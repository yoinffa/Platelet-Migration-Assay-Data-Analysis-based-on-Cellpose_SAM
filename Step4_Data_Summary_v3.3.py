#Version 3.3
# Combined Track and morphology analysis v3.1 (fixed)
#Combined data from Track_summary.csv, Morphology_summary.csv, and ForegroundRatio.csv

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import re
from collections import defaultdict
from datetime import datetime


def _ensure_abs_path(root_folder: str, path: str) -> str:
    """If user provides a relative output filename, save it into root_folder."""
    if not path:
        return path
    if os.path.isabs(path):
        return path
    return os.path.join(root_folder, path)


# Function 1: Track Summary
def Summary_Track_data(root_folder, threshold):
    import pandas as pd  # Delayed import

    if not root_folder:
        messagebox.showerror("Error", "Invalid input. Please provide root folder.")
        return

    if not os.path.isdir(root_folder):
        messagebox.showerror("Error", f"Root folder not found:\n{root_folder}")
        return

    # Fixed output filename
    output_file = os.path.join(root_folder, "Track_summary.csv")
    # Fixed file suffix
    file_suffix = ".csv"

    try:
        threshold = float(threshold)
    except ValueError:
        messagebox.showerror("Error", "Threshold must be a valid number.")
        return

    # Collect files
    all_files = []
    for dirpath, _, filenames in os.walk(root_folder):
        for f in filenames:
            if f.endswith(file_suffix):
                all_files.append(os.path.join(dirpath, f))

    # Expect: <prefix>_(CELLS|TRACKS)_masks_(CMG|IMG).csv
    pattern = re.compile(r"^(.*)_(CELLS|TRACKS)_masks_(CMG|IMG)\.csv$")
    file_groups = defaultdict(dict)

    file_processed = False
    for file in all_files:
        base = os.path.basename(file)
        match = pattern.match(base)
        if match:
            file_processed = True
            prefix, _, suffix = match.groups()
            file_groups[prefix][suffix] = file

    # Prepare result table (avoid concat warning)
    columns = ["Migration", "Adhesion", "Ratio", "Distance", "SD"]
    result_df = pd.DataFrame(columns=columns)

    skipped = 0
    for prefix, group in file_groups.items():
        cmg_file = group.get("CMG")
        img_file = group.get("IMG")

        if not (cmg_file and img_file):
            skipped += 1
            print(f"Skipping incomplete group: {prefix} (CMG or IMG missing)")
            continue

        # --- Migration from IMG (Longest Shortest Path > threshold)
        try:
            df_IMG = pd.read_csv(img_file, header=0, index_col=0)
            dc = "Longest Shortest Path"

            if dc not in df_IMG.columns:
                raise KeyError(f"Column '{dc}' not found in {img_file}")

            mask = df_IMG[dc] > threshold
            Migration = int(mask.sum())

            if mask.any():
                Migration_dc = float(df_IMG.loc[mask, dc].mean())
                Migration_sd = float(df_IMG.loc[mask, dc].std())
                # std can be NaN if only one value
                if pd.isna(Migration_sd):
                    Migration_sd = 0.0
            else:
                Migration_dc = 0.0
                Migration_sd = 0.0

        except Exception as e:
            print(f"[IMG ERROR] {prefix}: {e}")
            Migration = 0
            Migration_dc = 0.0
            Migration_sd = 0.0

        # --- Adhesion count from CMG rows
        try:
            df_CMG = pd.read_csv(cmg_file, header=0, index_col=0)
            if not df_CMG.empty:
                Adhesion = int(len(df_CMG))
                Ratio = min(100.0, (Migration / Adhesion * 100.0)) if Adhesion > 0 else 0.0
            else:
                Adhesion = 0
                Ratio = 0.0
        except Exception as e:
            print(f"[CMG ERROR] {prefix}: {e}")
            Adhesion = 0
            Ratio = 0.0

        # Use IMG filename (without path) as index
        idx = os.path.basename(img_file)
        result_df.loc[idx, columns] = [Migration, Adhesion, Ratio, Migration_dc, Migration_sd]

    # Round and write
    result_df = result_df.round(3)
    try:
        result_df.to_csv(output_file, index=True, lineterminator="\n")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to write track summary:\n{e}")
        return

    # Update ForegroundRatio.csv with Adhesion data
    if file_processed and len(result_df) > 0:
        update_foreground_ratio_with_adhesion(root_folder, output_file)

    if file_processed and len(result_df) > 0:
        messagebox.showinfo("Success", f"Track data processing complete!\nResults saved to:\n{output_file}")
    elif file_processed and len(result_df) == 0:
        messagebox.showwarning(
            "No Complete Groups",
            "Track files were found, but no complete (CMG + IMG) pairs were detected.\n"
            "Please check your file naming and suffix settings."
        )
    else:
        messagebox.showwarning("No Files Found", f"No matching track files found with suffix '{file_suffix}'.")


# Function 2: Morphology Summary
def Summary_Morphology_data(root_folder, include_df):
    import pandas as pd  # Delayed import

    if not root_folder:
        messagebox.showerror("Error", "Invalid input. Please provide root folder.")
        return

    if not os.path.isdir(root_folder):
        messagebox.showerror("Error", f"Root folder not found:\n{root_folder}")
        return

    # Fixed output filenames
    output_file = os.path.join(root_folder, "Morphology_summary.csv")  # Always generated (for Summary.csv)
    output_detail_file = os.path.join(root_folder, "Morphology_summary_detail.csv")  # Generated only if include_df=True
    # Fixed file suffix
    file_suffix = "CMG.csv"

    file_processed = False
    merged_df_mean = pd.DataFrame()  # For Morphology_summary.csv (mean values only)
    merged_df_detail = pd.DataFrame()  # For Morphology_summary_detail.csv (all detail data)

    for dirpath, _, filenames in os.walk(root_folder):
        for file in filenames:
            if file.endswith(file_suffix):
                file_processed = True
                full_path = os.path.join(dirpath, file)
                print(file)
                try:
                    df = pd.read_csv(full_path, header=0, index_col=0)
                except Exception as e:
                    print(f"[MORPH READ ERROR] {file}: {e}")
                    continue

                # Calculate mean values for each file
                mean_values = df.mean(numeric_only=True)
                mean_row = pd.DataFrame([mean_values], index=[file])

                # Always add mean row to merged_df_mean (for Morphology_summary.csv)
                merged_df_mean = pd.concat([merged_df_mean, mean_row], ignore_index=False)

                # If include_df is True, add all detail data to merged_df_detail
                if include_df:
                    # Add all rows from df with filename prefix
                    df_with_prefix = df.copy()
                    df_with_prefix.index = [f"{file}_{idx}" for idx in df.index]
                    merged_df_detail = pd.concat([merged_df_detail, df_with_prefix], ignore_index=False)

    merged_df_mean = merged_df_mean.round(3)
    if include_df:
        merged_df_detail = merged_df_detail.round(3)

    # Always save Morphology_summary.csv (required for Summary.csv calculation)
    try:
        merged_df_mean.to_csv(output_file, index=True, lineterminator="\n")
        print(f"Morphology_summary.csv saved: {output_file}")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to write morphology summary:\n{e}")
        return

    # Save Morphology_summary_detail.csv only if include_df is True
    if include_df:
        try:
            merged_df_detail.to_csv(output_detail_file, index=True, lineterminator="\n")
            print(f"Morphology_summary_detail.csv saved: {output_detail_file}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to write morphology detail summary:\n{e}")
            return

    if file_processed:
        if include_df:
            messagebox.showinfo("Success", 
                f"Processing complete!\n"
                f"Results saved to:\n{output_file}\n{output_detail_file}")
        else:
            messagebox.showinfo("Success", f"Processing complete!\nResults saved to:\n{output_file}")
    else:
        messagebox.showwarning(
            "No Files Found",
            f"No files with the specified suffix '{file_suffix}' were found in the selected folder."
        )


def update_foreground_ratio_with_adhesion(root_folder, track_summary_file):
    """
    Update ForegroundRatio.csv with Adhesion column from track_summary.csv
    and calculate foreground area per cell.
    """
    import pandas as pd
    
    # Locate ForegroundRatio.csv in root folder
    foreground_csv = os.path.join(root_folder, "ForegroundRatio.csv")
    
    if not os.path.exists(foreground_csv):
        print(f"Warning: ForegroundRatio.csv not found at {foreground_csv}")
        return
    
    if not os.path.exists(track_summary_file):
        print(f"Warning: Track summary file not found at {track_summary_file}")
        return
    
    try:
        # Read both CSVs
        df_fg = pd.read_csv(foreground_csv, index_col=0)
        df_track = pd.read_csv(track_summary_file, index_col=0)
        
        # Create a mapping from filename prefix to Adhesion value
        # Track summary index format: "prefix_S1_TRACKS_masks_IMG.csv"
        # ForegroundRatio index format: "prefix_S1_TRACKS_masks.tif"
        adhesion_map = {}
        
        for idx in df_track.index:
            # Extract prefix by removing "_IMG.csv" suffix
            # e.g., "prefix_S1_TRACKS_masks_IMG.csv" -> "prefix_S1_TRACKS_masks"
            if idx.endswith("_IMG.csv"):
                prefix = idx[:-8]  # Remove "_IMG.csv"
                adhesion_map[prefix] = df_track.loc[idx, "Adhesion"]
        
        # Add Adhesion column to ForegroundRatio dataframe
        adhesion_values = []
        for idx in df_fg.index:
            # ForegroundRatio index format: "prefix_S1_TRACKS_masks.tif"
            # Extract prefix by removing ".tif" suffix
            if idx.endswith(".tif"):
                prefix = idx[:-4]  # Remove ".tif"
            else:
                prefix = idx
            
            # Look up adhesion value
            adhesion = adhesion_map.get(prefix, 0)
            adhesion_values.append(adhesion)
        
        df_fg["Adhesion"] = adhesion_values
        
        # Calculate foreground area per cell
        # Avoid division by zero
        df_fg["Foreground Area Per Cell(um^2)"] = df_fg.apply(
            lambda row: row["ForegroundArea(um^2)"] / row["Adhesion"] if row["Adhesion"] > 0 else 0,
            axis=1
        )
        
        # Round numeric columns
        df_fg = df_fg.round(4)
        
        # Save updated ForegroundRatio.csv
        df_fg.to_csv(foreground_csv, index=True, lineterminator="\n")
        print(f"Successfully updated {foreground_csv} with Adhesion and Foreground Area Per Cell columns")
        
    except Exception as e:
        print(f"Error updating ForegroundRatio.csv: {e}")
        import traceback
        traceback.print_exc()


def extract_prefix_for_summary(filename):
    """
    Extract the prefix from filename before _S1, _S2, _S3, etc.
    Example: "2025_12_01_3F_1d5C_0.5_689ng_ml_dH_Out_S1_TRACKS_masks_IMG.csv"
    Returns: "2025_12_01_3F_1d5C_0.5_689ng_ml_dH_Out"
    """
    if filename is None or not isinstance(filename, str):
        return None
    
    # Match pattern: _S followed by one or more digits
    match = re.search(r'_S\d+_', filename)
    if match:
        # Return everything before _S[number]_
        return filename[:match.start()]
    
    # Fallback: try to find _S at the end
    match = re.search(r'_S\d+', filename)
    if match:
        return filename[:match.start()]
    
    return filename  # Return as-is if no pattern found


def calculate_summary_all(root_folder):
    """
    Process Track_summary.csv, Morphology_summary.csv, and ForegroundRatio.csv,
    group by prefix, calculate means, and save to Summary.csv in root_folder.
    Uses fixed filenames to ensure program stability.
    """
    import pandas as pd
    
    # Fixed filenames
    track_summary_file = os.path.join(root_folder, "Track_summary.csv")
    morphology_summary_file = os.path.join(root_folder, "Morphology_summary.csv")
    foreground_csv = os.path.join(root_folder, "ForegroundRatio.csv")
    summary_csv = os.path.join(root_folder, "Summary.csv")
    
    files_to_process = [
        (track_summary_file, "Track_"),
        (morphology_summary_file, "Morphology_"),
        (foreground_csv, "Foreground_")
    ]
    
    all_summaries = []
    
    # Process each file
    for filepath, prefix in files_to_process:
        if not os.path.exists(filepath):
            print(f"Warning: {filepath} not found. Skipping...")
            continue
        
        try:
            # For ForegroundRatio.csv, the first column is "FileName", not an index
            if "ForegroundRatio" in filepath:
                df = pd.read_csv(filepath)
                # Use FileName column as index
                if 'FileName' in df.columns:
                    df.set_index('FileName', inplace=True)
            else:
                # For other files, first column is the index
                df = pd.read_csv(filepath, index_col=0)
            
            print(f"\nProcessing {os.path.basename(filepath)} for summary...")
            print(f"  Loaded {len(df)} rows")
            
            # Extract prefix from index (filename)
            df['Prefix'] = df.index.map(extract_prefix_for_summary)
            
            # Remove rows where prefix extraction failed
            df = df[df['Prefix'].notna()]
            
            # Group by prefix and calculate mean for numeric columns
            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
            
            if len(numeric_cols) == 0:
                print(f"  Warning: No numeric columns found in {filepath}")
                continue
            
            # Calculate mean for each group
            summary_df = df.groupby('Prefix')[numeric_cols].mean()
            
            # Round to 3 decimal places (same as original)
            summary_df = summary_df.round(3)
            
            # Add prefix to column names if specified
            if prefix:
                summary_df.columns = [f"{prefix}{col}" for col in summary_df.columns]
            
            print(f"  Found {len(summary_df)} unique groups")
            all_summaries.append(summary_df)
            
        except Exception as e:
            print(f"Error processing {filepath} for summary: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    if len(all_summaries) == 0:
        print("\nWarning: No files were successfully processed for summary.")
        return
    
    # Merge all summaries on Prefix (index)
    print("\nMerging results for Summary.csv...")
    combined_df = all_summaries[0]
    
    for summary_df in all_summaries[1:]:
        combined_df = combined_df.join(summary_df, how='outer')
    
    # Sort by prefix for better readability
    combined_df = combined_df.sort_index()
    
    # Save to Summary.csv in root_folder
    combined_df.to_csv(summary_csv, index=True, lineterminator="\n")
    
    print(f"\n{'='*60}")
    print(f"Summary.csv generated successfully!")
    print(f"Total unique groups: {len(combined_df)}")
    print(f"Total columns: {len(combined_df.columns)}")
    print(f"Results saved to: {summary_csv}")
    print(f"{'='*60}")


def log_parameters(root_folder, output_track, file_suffix_track, threshold,
                   output_morphology, file_suffix_morphology, include_df):
    """Log all parameters to Step4_log.txt in the root_folder"""
    if root_folder:
        log_file = os.path.join(root_folder, "Step4_log.txt")
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        log_file = os.path.join(script_dir, "Step4_log.txt")

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    day_name = now.strftime("%A")
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Use "w" mode to overwrite old log file (clear previous contents)
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("Step4_Data_Summary_v3.3 Log\n")
            f.write(f"Date: {date_str} ({day_name})\n")
            f.write(f"Time: {time_str}\n")
            f.write(f"Full Timestamp: {timestamp}\n")
            f.write("=" * 80 + "\n\n")

            f.write("GENERAL SETTINGS:\n")
            f.write(f"  Root Folder: {root_folder}\n\n")

            f.write("TRACK SUMMARY CONFIGURATION:\n")
            f.write(f"  Output File: {output_track} \n")
            f.write(f"  File Suffix: {file_suffix_track}\n")
            f.write(f"  Threshold for Migration(μm): {threshold}\n\n")

            f.write("MORPHOLOGY SUMMARY CONFIGURATION:\n")
            f.write(f"  Output File: {output_morphology} \n")
            f.write(f"  File Suffix: {file_suffix_morphology}\n")
            f.write(f"  Include Full Dataframe: {include_df}\n\n")
            
            f.write("FINAL SUMMARY:\n")
            f.write(f"  Output File: Summary.csv \n\n")

            f.write("-" * 80 + "\n\n")
            f.flush()
    except Exception as e:
        error_msg = f"Warning: Could not write to log file: {e}\nLog file path: {log_file}"
        print(error_msg)
        try:
            messagebox.showwarning("Log Warning", error_msg)
        except:
            pass


# Master Summary
def Summary_all(root_folder, threshold, include_df):
    # Fixed output filenames
    output_track = "Track_summary.csv"
    output_morphology = "Morphology_summary.csv"
    # Fixed file suffixes
    file_suffix_track = ".csv"
    file_suffix_morphology = "CMG.csv"
    
    log_parameters(root_folder, output_track, file_suffix_track, threshold,
                   output_morphology, file_suffix_morphology, include_df)

    Summary_Track_data(root_folder, threshold)
    Summary_Morphology_data(root_folder, include_df)
    
    # Calculate summary from all generated CSV files (using fixed filenames)
    calculate_summary_all(root_folder)


def main():
    # GUI with Modern Styling
    root = tk.Tk()
    root.title("📊 Platelet Data Summary")
    root.geometry("750x650")
    root.configure(bg="#2b2b2b")

    COLORS = {
        "bg": "#2b2b2b",
        "fg": "#ffffff",
        "frame_bg": "#3c3c3c",
        "entry_bg": "#4a4a4a",
        "entry_fg": "#ffffff",
        "button_bg": "#4a9eff",
        "button_hover": "#6bb0ff",
        "button_fg": "#ffffff",
        "close_bg": "#ff6b6b",
        "close_hover": "#ff8787",
        "label_fg": "#e0e0e0",
        "accent": "#00d4ff",
        "separator": "#555555",
        "checkbox_bg": "#3c3c3c",
        "checkbox_fg": "#e0e0e0",
    }

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TFrame", background=COLORS["frame_bg"])
    style.configure("TLabel", background=COLORS["frame_bg"], foreground=COLORS["label_fg"], font=("Segoe UI", 9))
    style.configure("TEntry", fieldbackground=COLORS["entry_bg"], foreground=COLORS["entry_fg"], borderwidth=1, relief="solid")

    main_frame = tk.Frame(root, bg=COLORS["bg"], padx=20, pady=20)
    main_frame.pack(fill="both", expand=True)

    title_label = tk.Label(
        main_frame,
        text="📊 Platelet Data Summary",
        font=("Segoe UI", 18, "bold"),
        bg=COLORS["bg"],
        fg=COLORS["accent"],
    )
    title_label.pack(pady=(0, 20))

    # Root Folder
    folder_frame = tk.Frame(main_frame, bg=COLORS["frame_bg"], relief="flat", bd=2, padx=15, pady=12)
    folder_frame.pack(fill="x", pady=(0, 15))

    tk.Label(folder_frame, text="📁 Root Folder", font=("Segoe UI", 10, "bold"),
             bg=COLORS["frame_bg"], fg=COLORS["label_fg"]).grid(row=0, column=0, sticky="w", pady=(0, 8))

    root_folder_var = tk.StringVar()
    folder_entry = tk.Entry(
        folder_frame,
        textvariable=root_folder_var,
        width=55,
        bg=COLORS["entry_bg"],
        fg=COLORS["entry_fg"],
        insertbackground=COLORS["entry_fg"],
        font=("Segoe UI", 9),
        relief="flat",
        bd=5,
    )
    folder_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10))
    folder_frame.grid_columnconfigure(0, weight=1)

    browse_folder_btn = tk.Button(
        folder_frame,
        text="Browse",
        command=lambda: root_folder_var.set(filedialog.askdirectory()),
        bg=COLORS["button_bg"],
        fg=COLORS["button_fg"],
        font=("Segoe UI", 9, "bold"),
        relief="flat",
        bd=0,
        padx=15,
        pady=5,
        cursor="hand2",
        activebackground=COLORS["button_hover"],
        activeforeground=COLORS["button_fg"],
    )
    browse_folder_btn.grid(row=1, column=1)

    # Track Summary
    track_frame = tk.LabelFrame(
        main_frame,
        text="  📈 Track Summary Configuration  ",
        font=("Segoe UI", 11, "bold"),
        bg=COLORS["frame_bg"],
        fg=COLORS["accent"],
        relief="flat",
        bd=2,
        padx=15,
        pady=15,
    )
    track_frame.pack(fill="x", pady=(0, 15))

    tk.Label(track_frame, text="Output File:", bg=COLORS["frame_bg"], fg=COLORS["label_fg"],
             font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=5)

    # Fixed output filename (read-only display)
    track_output_label = tk.Label(
        track_frame,
        text="Track_summary.csv",
        bg=COLORS["frame_bg"],
        fg=COLORS["accent"],
        font=("Segoe UI", 9, "bold"),
        anchor="w",
    )
    track_output_label.grid(row=0, column=1, sticky="w", padx=(10, 30), pady=5)

    # Threshold for Migration in the same line
    tk.Label(track_frame, text="Threshold for Migration(μm):", bg=COLORS["frame_bg"], fg=COLORS["label_fg"],
             font=("Segoe UI", 9), anchor="w").grid(row=0, column=2, sticky="w", padx=(10, 5), pady=5)

    threshold_var = tk.StringVar(value="3")
    threshold_entry = tk.Entry(
        track_frame,
        textvariable=threshold_var,
        width=15,
        bg=COLORS["entry_bg"],
        fg=COLORS["entry_fg"],
        insertbackground=COLORS["entry_fg"],
        font=("Segoe UI", 9),
        relief="flat",
        bd=5,
    )
    threshold_entry.grid(row=0, column=3, padx=5, pady=5, sticky="w")
    track_frame.grid_columnconfigure(1, weight=1)

    # Morphology Summary
    morph_frame = tk.LabelFrame(
        main_frame,
        text="  🔬 Morphology Summary Configuration  ",
        font=("Segoe UI", 11, "bold"),
        bg=COLORS["frame_bg"],
        fg=COLORS["accent"],
        relief="flat",
        bd=2,
        padx=15,
        pady=15,
    )
    morph_frame.pack(fill="x", pady=(0, 15))

    tk.Label(morph_frame, text="Output File:", bg=COLORS["frame_bg"], fg=COLORS["label_fg"],
             font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=5)

    # Fixed output filename (read-only display)
    morph_output_label = tk.Label(
        morph_frame,
        text="Morphology_summary.csv",
        bg=COLORS["frame_bg"],
        fg=COLORS["accent"],
        font=("Segoe UI", 9, "bold"),
        anchor="w",
    )
    morph_output_label.grid(row=0, column=1, sticky="w", padx=(10, 30), pady=5)

    # Show data for each cell checkbox in the same line
    include_df_var = tk.BooleanVar(value=False)
    checkbox = tk.Checkbutton(
        morph_frame,
        text="Show morphology detail of each cell",
        variable=include_df_var,
        bg=COLORS["checkbox_bg"],
        fg=COLORS["checkbox_fg"],
        selectcolor=COLORS["entry_bg"],
        activebackground=COLORS["checkbox_bg"],
        activeforeground=COLORS["checkbox_fg"],
        font=("Segoe UI", 9),
        cursor="hand2",
    )
    checkbox.grid(row=0, column=2, sticky="w", padx=(10, 5), pady=5)
    morph_frame.grid_columnconfigure(1, weight=1)

    # Final Summary
    summary_frame = tk.LabelFrame(
        main_frame,
        text="  📋 Final Summary Output  ",
        font=("Segoe UI", 11, "bold"),
        bg=COLORS["frame_bg"],
        fg=COLORS["accent"],
        relief="flat",
        bd=2,
        padx=15,
        pady=15,
    )
    summary_frame.pack(fill="x", pady=(0, 15))

    tk.Label(summary_frame, text="Summary File:", bg=COLORS["frame_bg"], fg=COLORS["label_fg"],
             font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", pady=5)

    summary_output_label = tk.Label(
        summary_frame,
        text="Summary.csv",
        bg=COLORS["frame_bg"],
        fg=COLORS["accent"],
        font=("Segoe UI", 9, "bold"),
        anchor="w",
    )
    summary_output_label.grid(row=0, column=1, sticky="ew", padx=(10, 10), pady=5)
    summary_frame.grid_columnconfigure(1, weight=1)

    tk.Label(summary_frame, 
             text="Note: Summary.csv combines data from Track_summary.csv, Morphology_summary.csv, and ForegroundRatio.csv",
             bg=COLORS["frame_bg"],
             fg=COLORS["label_fg"],
             font=("Segoe UI", 8, "italic"),
             wraplength=600,
             justify="left").grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(5, 0))

    # Buttons
    button_frame = tk.Frame(main_frame, bg=COLORS["bg"])
    button_frame.pack(fill="x", pady=(10, 0))

    run_btn = tk.Button(
        button_frame,
        text="▶  Run ",
        command=lambda: Summary_all(
            root_folder_var.get(),
            threshold_var.get(),
            include_df_var.get(),
        ),
        bg=COLORS["button_bg"],
        fg=COLORS["button_fg"],
        font=("Segoe UI", 11, "bold"),
        relief="flat",
        bd=0,
        width=16,  
        height=2,  
        padx=30,
        pady=12,
        cursor="hand2",
        activebackground=COLORS["button_hover"],
        activeforeground=COLORS["button_fg"],
    )
    run_btn.pack(side="left", padx=(0, 15))

    close_btn = tk.Button(
        button_frame,
        text="✕  Close",
        command=root.destroy,
        bg=COLORS["close_bg"],
        fg=COLORS["button_fg"],
        font=("Segoe UI", 11, "bold"),
        relief="flat",
        bd=0,
        width=16,  
        height=2, 
        padx=30,
        pady=12,
        cursor="hand2",
        activebackground=COLORS["close_hover"],
        activeforeground=COLORS["button_fg"],
    )
    close_btn.pack(side="left")

    root.bind(
        "<Return>",
        lambda event: Summary_all(
            root_folder_var.get(),
            threshold_var.get(),
            include_df_var.get(),
        ),
    )

    root.mainloop()


if __name__ == "__main__":
    main()
