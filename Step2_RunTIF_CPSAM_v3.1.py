# Run Cellpose for TRACKS and CELLS v3
# FIXED: Fiji/ImageJ unit missing -> now written via ImageJ metadata (metadata={'unit':'micron'})
# FIXED: remove description=... when imagej=True (avoids tifffile warning and prevents unit loss)

import os, sys
from pathlib import Path

if getattr(sys, "frozen", False):
    root = Path(sys.executable).parent
    for p in [root / "torch" / "lib", root / "Library" / "bin"]:
        if p.exists():
            os.add_dll_directory(str(p))
            
import os
import sys
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# ----------------------------- helpers -----------------------------
def safe_rational(tag_value, default=(1, 1)):
    """Normalize TIFF rational tag values into a (num, den) tuple."""
    try:
        if isinstance(tag_value, tuple) and len(tag_value) == 2:
            return (int(tag_value[0]), int(tag_value[1]))
        if hasattr(tag_value, "numerator") and hasattr(tag_value, "denominator"):
            return (int(tag_value.numerator), int(tag_value.denominator))
        if isinstance(tag_value, (int, float)):
            return (int(tag_value), 1)
    except Exception:
        pass
    return default


def microns_per_pixel_from_tiff(res_tuple, resunit_val):
    """
    TIFF XResolution/YResolution are RATIONALs representing pixels per unit.
    res_tuple: (num, den) where num/den = pixels per unit
    resunit_val: 2=inches, 3=centimeter, 1/None=unknown
    """
    try:
        if not isinstance(res_tuple, tuple) or len(res_tuple) != 2:
            return 1.0
        num, den = res_tuple
        if den == 0:
            return 1.0
        px_per_unit = num / den
        if px_per_unit == 0:
            return 1.0

        if resunit_val == 2:        # inch
            microns_per_unit = 25400.0
        elif resunit_val == 3:      # cm
            microns_per_unit = 10000.0
        else:
            return 1.0

        return microns_per_unit / px_per_unit
    except Exception:
        return 1.0


def extract_imagej_unit_from_description(desc: str):
    """
    If input is an ImageJ TIFF, unit often appears in ImageDescription as 'unit=...'.
    Return that unit string (e.g., 'micron') or None.
    """
    if not isinstance(desc, str) or not desc.strip():
        return None
    for line in desc.splitlines():
        if line.startswith("unit="):
            return line.split("=", 1)[1].strip() or None
    return None


# ----------------------------- core -----------------------------
def Run_Cellpose(root_folder, file_suffix, model_path, flow_thres, cellprob_thres, diameter=None, niter=1000):
    if not root_folder or not file_suffix or not model_path:
        messagebox.showerror("Error", "Missing input. Please check all fields.")
        return

    from tifffile import imread, TiffFile, imwrite  # delayed import
    from cellpose import models  # delayed import

    output_dir = Path(root_folder)

    try:
        # Try GPU first, fall back to CPU if GPU fails
        try:
            model = models.CellposeModel(gpu=True, pretrained_model=model_path)
            print("Using GPU for inference")
        except Exception as gpu_error:
            print(f"GPU initialization failed: {gpu_error}")
            print("Falling back to CPU mode")
            model = models.CellposeModel(gpu=False, pretrained_model=model_path)
    except Exception as e:
        messagebox.showerror("Error", f"Model loading failed:\n{e}")
        return

    eval_params = {
        "batch_size": 32,
        "flow_threshold": float(flow_thres),
        "cellprob_threshold": float(cellprob_thres),
        "normalize": {"tile_norm_blocksize": 0},
    }

    if diameter is not None and str(diameter).strip() != "":
        try:
            eval_params["diameter"] = float(diameter)
        except (ValueError, TypeError):
            messagebox.showerror("Error", f"Invalid diameter value: {diameter}\nExpected a number (or leave empty for auto-detect)")
            return

    if niter is not None:
        try:
            eval_params["niter"] = int(niter)
        except (ValueError, TypeError):
            messagebox.showerror("Error", f"Invalid niter value: {niter}")
            return

    for dirpath, _, filenames in os.walk(root_folder):
        for file in filenames:
            if not file.endswith(file_suffix):
                continue

            try:
                print(f"Processing {file}...")
                f = os.path.join(dirpath, file)
                f_path = Path(f)
                img = imread(f)

                masks, flows, styles = model.eval(img, **eval_params)

                # Read original TIFF tags (to preserve scale numbers)
                with TiffFile(f) as tif:
                    page = tif.pages[0]
                    xres_tag = page.tags.get("XResolution", None)
                    yres_tag = page.tags.get("YResolution", None)
                    resunit_tag = page.tags.get("ResolutionUnit", None)
                    desc_tag = page.tags.get("ImageDescription", None)

                    xres_val = xres_tag.value if xres_tag is not None and hasattr(xres_tag, "value") else (1, 1)
                    yres_val = yres_tag.value if yres_tag is not None and hasattr(yres_tag, "value") else (1, 1)
                    resunit_val = resunit_tag.value if resunit_tag is not None and hasattr(resunit_tag, "value") else 1

                    input_description = None
                    if desc_tag is not None:
                        input_description = desc_tag.value if hasattr(desc_tag, "value") else desc_tag
                        if isinstance(input_description, bytes):
                            try:
                                input_description = input_description.decode("utf-8", errors="replace")
                            except Exception:
                                input_description = input_description.decode("latin-1", errors="replace")

                    if input_description:
                        print(f"Found ImageDescription in input: {str(input_description)[:200]}")
                    else:
                        print(f"No ImageDescription found in input file: {file}")

                xres_tuple = safe_rational(xres_val, default=(1, 1))
                yres_tuple = safe_rational(yres_val, default=(1, 1))

                # Compute microns per pixel (optional; we set unit via metadata, spacing mainly for completeness)
                mpp_x = microns_per_pixel_from_tiff(xres_tuple, resunit_val)
                mpp_y = microns_per_pixel_from_tiff(yres_tuple, resunit_val)

                # Prefer the unit used by the input ImageJ TIFF if present (your input shows unit=micron)
                unit_from_input = extract_imagej_unit_from_description(input_description) if input_description else None
                # IMPORTANT: ImageJ understands "micron" best (your input already uses it)
                unit_out = unit_from_input if unit_from_input else "micron"

                mask_out = output_dir / (f_path.stem + "_masks.tif")

                # Write ImageJ TIFF correctly:
                # - Use imagej=True
                # - DO NOT pass description=... (tifffile will ignore it and warn)
                # - Provide unit via metadata so Fiji shows it (not "pixel")
                # - Preserve original resolution + resolutionunit so numeric scale remains unchanged
                # - Use uint16 so instance IDs won't wrap at 255
                imwrite(
                    mask_out,
                    masks.astype("uint16"),
                    imagej=True,
                    resolution=(xres_tuple, yres_tuple),
                    resolutionunit=resunit_val,
                    metadata={
                        "unit": unit_out,      # <- this fixes the missing unit in Fiji
                        # ImageJ has only one 'spacing' field (often Z). We set it to X as a safe default.
                        # Pixel width/height come from resolution tags; this keeps your scale number consistent.
                        "spacing": float(mpp_x),
                    },
                )

            except Exception as e:
                print(f"Error processing {file}: {e}")


def log_parameters(root_folder, Tracks_model_path, Tracks_flow_thres, Tracks_prob_thres,
                   Tracks_diameter, Tracks_niter, Cells_model_path, Cells_flow_thres,
                   Cells_prob_thres, Cells_diameter, Cells_niter):
    """Log all parameters to Step2_log.txt in the root_folder"""
    if root_folder:
        log_file = os.path.join(root_folder, "Step2_log.txt")
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        log_file = os.path.join(script_dir, "Step2_log.txt")

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    day_name = now.strftime("%A")
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Use "w" mode to overwrite old log file (clear previous contents)
        with open(log_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("Step2_RunTIF_CPSAM_v3.1 Log\n")
            f.write(f"Date: {date_str} ({day_name})\n")
            f.write(f"Time: {time_str}\n")
            f.write(f"Full Timestamp: {timestamp}\n")
            f.write("=" * 80 + "\n\n")

            f.write("GENERAL SETTINGS:\n")
            f.write(f"  Root Folder: {root_folder}\n\n")

            f.write("TRACKS CONFIGURATION:\n")
            f.write(f"  Model Path: {Tracks_model_path}\n")
            f.write(f"  Flow Threshold: {Tracks_flow_thres}\n")
            f.write(f"  Cellprob Threshold: {Tracks_prob_thres}\n")
            f.write(f"  Diameter: {Tracks_diameter if Tracks_diameter else 'Auto (None)'}\n")
            f.write(f"  Niter Dynamics: {Tracks_niter}\n\n")

            f.write("CELLS CONFIGURATION:\n")
            f.write(f"  Model Path: {Cells_model_path}\n")
            f.write(f"  Flow Threshold: {Cells_flow_thres}\n")
            f.write(f"  Cellprob Threshold: {Cells_prob_thres}\n")
            f.write(f"  Diameter: {Cells_diameter if Cells_diameter else 'Auto (None)'}\n")
            f.write(f"  Niter Dynamics: {Cells_niter}\n\n")

            f.write("-" * 80 + "\n\n")
            f.flush()
    except Exception as e:
        error_msg = f"Warning: Could not write to log file: {e}\nLog file path: {log_file}"
        print(error_msg)
        try:
            messagebox.showwarning("Log Warning", error_msg)
        except Exception:
            pass


def Run_Cellpose_sum(root_folder,
                     Tracks_model_path, Tracks_flow_thres, Tracks_prob_thres, Tracks_diameter, Tracks_niter,
                     Cells_model_path, Cells_flow_thres, Cells_prob_thres, Cells_diameter, Cells_niter):
    log_parameters(root_folder, Tracks_model_path, Tracks_flow_thres, Tracks_prob_thres,
                   Tracks_diameter, Tracks_niter, Cells_model_path, Cells_flow_thres,
                   Cells_prob_thres, Cells_diameter, Cells_niter)

    try:
        Run_Cellpose(root_folder, "_TRACKS.tif", Tracks_model_path, Tracks_flow_thres, Tracks_prob_thres,
                     Tracks_diameter, Tracks_niter)
        Run_Cellpose(root_folder, "_CELLS.tif", Cells_model_path, Cells_flow_thres, Cells_prob_thres,
                     Cells_diameter, Cells_niter)
        messagebox.showinfo("Finished", "Cellpose processing complete!")
    except Exception as e:
        messagebox.showerror("Error", f"Processing failed: {e}")


# ----------------------------- GUI -----------------------------
root = tk.Tk()
root.title("🔬 Cellpose Processor - TRACKS & CELLS")
root.geometry("750x700")
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
    text="🔬 Cellpose Image Processor",
    font=("Segoe UI", 18, "bold"),
    bg=COLORS["bg"],
    fg=COLORS["accent"],
)
title_label.pack(pady=(0, 20))

# Root Folder
folder_frame = tk.Frame(main_frame, bg=COLORS["frame_bg"], relief="flat", bd=2, padx=15, pady=12)
folder_frame.pack(fill="x", pady=(0, 15))

tk.Label(
    folder_frame,
    text="📁 Root Folder",
    font=("Segoe UI", 10, "bold"),
    bg=COLORS["frame_bg"],
    fg=COLORS["label_fg"],
).grid(row=0, column=0, sticky="w", pady=(0, 8))

folder_path = tk.StringVar()
folder_entry = tk.Entry(
    folder_frame,
    textvariable=folder_path,
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
    command=lambda: folder_path.set(filedialog.askdirectory()),
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

# TRACKS Section
tracks_frame = tk.LabelFrame(
    main_frame,
    text="  🎯 TRACKS Configuration  ",
    font=("Segoe UI", 11, "bold"),
    bg=COLORS["frame_bg"],
    fg=COLORS["accent"],
    relief="flat",
    bd=2,
    padx=15,
    pady=15,
)
tracks_frame.pack(fill="x", pady=(0, 15))

tk.Label(tracks_frame, text="Model Path:", bg=COLORS["frame_bg"], fg=COLORS["label_fg"], font=("Segoe UI", 9)).grid(
    row=0, column=0, sticky="w", pady=5
)
tracks_model_path = tk.StringVar()
tracks_model_entry = tk.Entry(
    tracks_frame,
    textvariable=tracks_model_path,
    width=50,
    bg=COLORS["entry_bg"],
    fg=COLORS["entry_fg"],
    insertbackground=COLORS["entry_fg"],
    font=("Segoe UI", 9),
    relief="flat",
    bd=5,
)
tracks_model_entry.grid(row=0, column=1, sticky="ew", padx=(10, 10), pady=5)
tracks_frame.grid_columnconfigure(1, weight=1)

tracks_select_btn = tk.Button(
    tracks_frame,
    text="Select",
    command=lambda: tracks_model_path.set(filedialog.askopenfilename()),
    bg=COLORS["button_bg"],
    fg=COLORS["button_fg"],
    font=("Segoe UI", 8),
    relief="flat",
    bd=0,
    padx=12,
    pady=4,
    cursor="hand2",
    activebackground=COLORS["button_hover"],
)
tracks_select_btn.grid(row=0, column=2, pady=5)

params_frame = tk.Frame(tracks_frame, bg=COLORS["frame_bg"])
params_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))

tk.Label(params_frame, text="Flow Threshold:", bg=COLORS["frame_bg"], fg=COLORS["label_fg"], font=("Segoe UI", 9),
         width=18, anchor="w").grid(row=0, column=0, sticky="w", padx=5, pady=5)
tracks_flow_entry = tk.Entry(params_frame, width=15, bg=COLORS["entry_bg"], fg=COLORS["entry_fg"],
                             insertbackground=COLORS["entry_fg"], font=("Segoe UI", 9), relief="flat", bd=5)
tracks_flow_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
tracks_flow_entry.insert(0, "0.8")

tk.Label(params_frame, text="Cellprob Threshold:", bg=COLORS["frame_bg"], fg=COLORS["label_fg"], font=("Segoe UI", 9),
         width=18, anchor="w").grid(row=0, column=2, sticky="w", padx=5, pady=5)
tracks_prob_entry = tk.Entry(params_frame, width=15, bg=COLORS["entry_bg"], fg=COLORS["entry_fg"],
                             insertbackground=COLORS["entry_fg"], font=("Segoe UI", 9), relief="flat", bd=5)
tracks_prob_entry.grid(row=0, column=3, padx=5, pady=5, sticky="w")
tracks_prob_entry.insert(0, "0")

tk.Label(params_frame, text="Diameter (px):", bg=COLORS["frame_bg"], fg=COLORS["label_fg"], font=("Segoe UI", 9),
         width=18, anchor="w").grid(row=1, column=0, sticky="w", padx=5, pady=5)
tracks_diameter_entry = tk.Entry(params_frame, width=15, bg=COLORS["entry_bg"], fg=COLORS["entry_fg"],
                                 insertbackground=COLORS["entry_fg"], font=("Segoe UI", 9), relief="flat", bd=5)
tracks_diameter_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
tracks_diameter_entry.insert(0, "")

tk.Label(params_frame, text="Niter Dynamics:", bg=COLORS["frame_bg"], fg=COLORS["label_fg"], font=("Segoe UI", 9),
         width=18, anchor="w").grid(row=1, column=2, sticky="w", padx=5, pady=5)
tracks_niter_entry = tk.Entry(params_frame, width=15, bg=COLORS["entry_bg"], fg=COLORS["entry_fg"],
                              insertbackground=COLORS["entry_fg"], font=("Segoe UI", 9), relief="flat", bd=5)
tracks_niter_entry.grid(row=1, column=3, padx=5, pady=5, sticky="w")
tracks_niter_entry.insert(0, "1000")

# CELLS Section
cells_frame = tk.LabelFrame(
    main_frame,
    text="  🧪 CELLS Configuration  ",
    font=("Segoe UI", 11, "bold"),
    bg=COLORS["frame_bg"],
    fg=COLORS["accent"],
    relief="flat",
    bd=2,
    padx=15,
    pady=15,
)
cells_frame.pack(fill="x", pady=(0, 15))

tk.Label(cells_frame, text="Model Path:", bg=COLORS["frame_bg"], fg=COLORS["label_fg"], font=("Segoe UI", 9)).grid(
    row=0, column=0, sticky="w", pady=5
)
cells_model_path = tk.StringVar()
cells_model_entry = tk.Entry(
    cells_frame,
    textvariable=cells_model_path,
    width=50,
    bg=COLORS["entry_bg"],
    fg=COLORS["entry_fg"],
    insertbackground=COLORS["entry_fg"],
    font=("Segoe UI", 9),
    relief="flat",
    bd=5,
)
cells_model_entry.grid(row=0, column=1, sticky="ew", padx=(10, 10), pady=5)
cells_frame.grid_columnconfigure(1, weight=1)

cells_select_btn = tk.Button(
    cells_frame,
    text="Select",
    command=lambda: cells_model_path.set(filedialog.askopenfilename()),
    bg=COLORS["button_bg"],
    fg=COLORS["button_fg"],
    font=("Segoe UI", 8),
    relief="flat",
    bd=0,
    padx=12,
    pady=4,
    cursor="hand2",
    activebackground=COLORS["button_hover"],
)
cells_select_btn.grid(row=0, column=2, pady=5)

cells_params_frame = tk.Frame(cells_frame, bg=COLORS["frame_bg"])
cells_params_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))

tk.Label(cells_params_frame, text="Flow Threshold:", bg=COLORS["frame_bg"], fg=COLORS["label_fg"], font=("Segoe UI", 9),
         width=18, anchor="w").grid(row=0, column=0, sticky="w", padx=5, pady=5)
cells_flow_entry = tk.Entry(cells_params_frame, width=15, bg=COLORS["entry_bg"], fg=COLORS["entry_fg"],
                            insertbackground=COLORS["entry_fg"], font=("Segoe UI", 9), relief="flat", bd=5)
cells_flow_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
cells_flow_entry.insert(0, "0.4")

tk.Label(cells_params_frame, text="Cellprob Threshold:", bg=COLORS["frame_bg"], fg=COLORS["label_fg"], font=("Segoe UI", 9),
         width=18, anchor="w").grid(row=0, column=2, sticky="w", padx=5, pady=5)
cells_prob_entry = tk.Entry(cells_params_frame, width=15, bg=COLORS["entry_bg"], fg=COLORS["entry_fg"],
                            insertbackground=COLORS["entry_fg"], font=("Segoe UI", 9), relief="flat", bd=5)
cells_prob_entry.grid(row=0, column=3, padx=5, pady=5, sticky="w")
cells_prob_entry.insert(0, "0")

tk.Label(cells_params_frame, text="Diameter (px):", bg=COLORS["frame_bg"], fg=COLORS["label_fg"], font=("Segoe UI", 9),
         width=18, anchor="w").grid(row=1, column=0, sticky="w", padx=5, pady=5)
cells_diameter_entry = tk.Entry(cells_params_frame, width=15, bg=COLORS["entry_bg"], fg=COLORS["entry_fg"],
                                insertbackground=COLORS["entry_fg"], font=("Segoe UI", 9), relief="flat", bd=5)
cells_diameter_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
cells_diameter_entry.insert(0, "")

tk.Label(cells_params_frame, text="Niter Dynamics:", bg=COLORS["frame_bg"], fg=COLORS["label_fg"], font=("Segoe UI", 9),
         width=18, anchor="w").grid(row=1, column=2, sticky="w", padx=5, pady=5)
cells_niter_entry = tk.Entry(cells_params_frame, width=15, bg=COLORS["entry_bg"], fg=COLORS["entry_fg"],
                             insertbackground=COLORS["entry_fg"], font=("Segoe UI", 9), relief="flat", bd=5)
cells_niter_entry.grid(row=1, column=3, padx=5, pady=5, sticky="w")
cells_niter_entry.insert(0, "1000")

# Buttons
button_frame = tk.Frame(main_frame, bg=COLORS["bg"])
button_frame.pack(fill="x", pady=(10, 0))

run_btn = tk.Button(
    button_frame,
    text="▶  Run Both Models",
    command=lambda: Run_Cellpose_sum(
        folder_path.get(),
        tracks_model_path.get(), float(tracks_flow_entry.get()), float(tracks_prob_entry.get()),
        tracks_diameter_entry.get() if tracks_diameter_entry.get().strip() else None,
        int(tracks_niter_entry.get()) if tracks_niter_entry.get().strip() else 1000,
        cells_model_path.get(), float(cells_flow_entry.get()), float(cells_prob_entry.get()),
        cells_diameter_entry.get() if cells_diameter_entry.get().strip() else None,
        int(cells_niter_entry.get()) if cells_niter_entry.get().strip() else 1000
    ),
    bg=COLORS["button_bg"],
    fg=COLORS["button_fg"],
    font=("Segoe UI", 11, "bold"),
    relief="flat",
    bd=0,
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
    command=lambda: (root.destroy(), sys.exit()),
    bg=COLORS["close_bg"],
    fg=COLORS["button_fg"],
    font=("Segoe UI", 11, "bold"),
    relief="flat",
    bd=0,
    padx=30,
    pady=12,
    cursor="hand2",
    activebackground=COLORS["close_hover"],
    activeforeground=COLORS["button_fg"],
)
close_btn.pack(side="left")

root.protocol("WM_DELETE_WINDOW", lambda: (root.destroy(), sys.exit()))
root.mainloop()
