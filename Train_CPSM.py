"""
CellPoseSAM Training Script
Train and test using train and test folders

Key Improvements:
- Use pretrained model: Start from a good pretrained model instead of training from scratch
- Increase training epochs: At least 100 epochs, can train 150-200 epochs if loss is still decreasing
- Lower weight decay: Use 0.00001 instead of 0.1 to reduce overfitting
- Increase images per epoch: Set to 2-4 times the training set size to improve generalization
- Monitor training process: Observe changes in train loss and test loss

Example usage:
if args.nimg_per_epoch is None:
        nimg_per_epoch = max(8, len(train_data) * 2)  # At least 8 images, or 2 times the training set size
    else:
        nimg_per_epoch = args.nimg_per_epoch
        
python Train_CPSM.py `
    --train_dir train `
    --test_dir test `
    --pretrained_model "./pretrain_models/cpsam" `
    --model_name new_model `
    --n_epochs 150 `
    --batch_size 2 `
    --learning_rate 1e-5 `
    --weight_decay 0.00001 `
    --nimg_per_epoch 100
"""
import numpy as np
from cellpose import models, core, io, train
from pathlib import Path
from tqdm import trange
import matplotlib.pyplot as plt
from natsort import natsorted
import argparse
import os

io.logger_setup()  # run this to get printing of progress

def main():
    parser = argparse.ArgumentParser(description="Train CellPoseSAM model")
    parser.add_argument("--train_dir", type=str, default="train", help="Training data directory")
    parser.add_argument("--test_dir", type=str, default="test", help="Test data directory")
    parser.add_argument("--masks_ext", type=str, default="_seg.npy", help="Label file extension")
    parser.add_argument("--model_name", type=str, default="new_model", help="Model name")
    parser.add_argument("--pretrained_model", type=str, default="./pretrain_models", help="Pretrained model path (default: ./pretrain_models, set to None to not use pretrained model)")
    parser.add_argument("--n_epochs", type=int, default=100, help="Number of training epochs (default: 100, recommend at least 100 epochs for better results)")
    parser.add_argument("--learning_rate", type=float, default=1e-5, help="Learning rate (default: 1e-5)")
    parser.add_argument("--weight_decay", type=float, default=0.00001, help="Weight decay (default: 0.00001, helps reduce overfitting)")
    parser.add_argument("--batch_size", type=int, default=2, help="Batch size (default: 2, adjust according to GPU memory)")
    parser.add_argument("--nimg_per_epoch", type=int, default=None, help="Number of images per epoch (default: auto-calculated, recommend 2-4 times the training set size)")
    parser.add_argument("--gpu", action="store_true", default=True, help="Use GPU")
    parser.add_argument("--check_gpu", action="store_true", default=False, help="Check if GPU is available")
    parser.add_argument("--save_every", type=int, default=10, help="Save model every N epochs (default: 10)")
    
    args = parser.parse_args()
    
    # Check GPU
    if args.check_gpu:
        if core.use_gpu() == False:
            raise ImportError("No GPU access, change your runtime")
        print("GPU is available")
    else:
        print(f"Using GPU: {args.gpu}")
    
    # Check if directories exist
    train_dir = Path(args.train_dir)
    test_dir = Path(args.test_dir)
    
    if not train_dir.exists():
        raise FileNotFoundError(f"Training directory does not exist: {train_dir}")
    if not test_dir.exists():
        raise FileNotFoundError(f"Test directory does not exist: {test_dir}")
    
    print(f"Train directory: {train_dir}")
    print(f"Test directory: {test_dir}")
    
    # Create model - supports loading from pretrained model
    if args.pretrained_model and args.pretrained_model.lower() != "none":
        pretrained_path = Path(args.pretrained_model)
        
        # Check if path exists
        if pretrained_path.exists():
            print(f"Loading pretrained model from: {pretrained_path}")
            model = models.CellposeModel(gpu=args.gpu, pretrained_model=str(pretrained_path))
        else:
            # Try to find in default cellpose directory
            default_path = Path.home() / ".cellpose" / "models" / args.pretrained_model
            if default_path.exists():
                pretrained_path = default_path
                print(f"Found pretrained model at default location: {pretrained_path}")
                model = models.CellposeModel(gpu=args.gpu, pretrained_model=str(pretrained_path))
            else:
                # Try to use model name (CellPose will search automatically)
                print(f"Warning: Pretrained model not found at {args.pretrained_model}")
                print(f"Trying to load by name (CellPose will search automatically)...")
                try:
                    model = models.CellposeModel(gpu=args.gpu, pretrained_model=args.pretrained_model)
                except Exception as e:
                    print(f"Error loading pretrained model: {e}")
                    print("Creating new model instead...")
                    model = models.CellposeModel(gpu=args.gpu)
    else:
        print("Creating new model (no pretrained model specified)")
        model = models.CellposeModel(gpu=args.gpu)
    
    # Load training and test data
    print(f"Loading data with mask filter: {args.masks_ext}")
    output = io.load_train_test_data(
        str(train_dir), 
        str(test_dir), 
        mask_filter=args.masks_ext
    )
    train_data, train_labels, _, test_data, test_labels, _ = output
    
    print(f"Loaded {len(train_data)} training images")
    print(f"Loaded {len(test_data)} test images")
    
    if len(train_data) == 0:
        raise ValueError("No training data found. Check your train directory and mask_filter.")
    
    # Calculate number of images per epoch
    # Recommend using more images to improve model generalization
    if args.nimg_per_epoch is None:
        nimg_per_epoch = max(8, len(train_data) * 2)  # At least 8 images, or 2 times the training set size
    else:
        nimg_per_epoch = args.nimg_per_epoch
    
    # Train model
    print(f"\nStarting training...")
    print(f"Model name: {args.model_name}")
    print(f"Epochs: {args.n_epochs}")
    print(f"Learning rate: {args.learning_rate}")
    print(f"Batch size: {args.batch_size}")
    print(f"Weight decay: {args.weight_decay}")
    print(f"Images per epoch: {nimg_per_epoch}")
    print(f"Training set size: {len(train_data)}")
    print(f"Test set size: {len(test_data)}")
    print(f"\nTraining tips:")
    print(f"  - More epochs (100+) usually lead to better results")
    print(f"  - Lower weight_decay (0.00001) helps prevent overfitting")
    print(f"  - More images per epoch improves generalization")
    print(f"  - Use pretrained model for better starting point")
    
    new_model_path, train_losses, test_losses = train.train_seg(
        model.net,
        train_data=train_data,
        train_labels=train_labels,
        test_data=test_data,      # Add test set for validation
        test_labels=test_labels,  # Add test set labels
        batch_size=args.batch_size,
        n_epochs=args.n_epochs,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        nimg_per_epoch=nimg_per_epoch,
        model_name=args.model_name
    )
    
    print(f"\nTraining completed!")
    print(f"Model saved to: {new_model_path}")
    print(f"Final train loss: {train_losses[-1] if len(train_losses) > 0 else 'N/A'}")
    print(f"Final test loss: {test_losses[-1] if len(test_losses) > 0 else 'N/A'}")
    
    # Analyze training process
    if len(train_losses) > 0 and len(test_losses) > 0:
        print(f"\nTraining analysis:")
        print(f"  Initial train loss: {train_losses[0]:.6f}")
        print(f"  Final train loss: {train_losses[-1]:.6f}")
        if train_losses[0] > 0:
            print(f"  Loss reduction: {((train_losses[0] - train_losses[-1]) / train_losses[0] * 100):.2f}%")
        print(f"  Initial test loss: {test_losses[0]:.6f}")
        print(f"  Final test loss: {test_losses[-1]:.6f}")
        if test_losses[0] > 0:
            if test_losses[-1] < test_losses[0]:
                print(f"  Test loss reduction: {((test_losses[0] - test_losses[-1]) / test_losses[0] * 100):.2f}%")
            else:
                print(f"  Warning: Test loss increased, model may be overfitting")
    
    print(f"\nTo improve prediction accuracy:")
    print(f"  1. Train for more epochs if loss is still decreasing")
    print(f"  2. Use a better pretrained model as starting point")
    print(f"  3. Increase nimg_per_epoch for better generalization")
    print(f"  4. Adjust learning_rate if loss is not decreasing")
    print(f"  5. Use flow_threshold=0 in prediction to detect all instances")

if __name__ == "__main__":
    main()