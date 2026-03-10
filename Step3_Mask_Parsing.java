// Version15.3 - Background Batch (Scheme B: carve seam between touching labels for Cellpose instance masks)
// CELLS: Cellpose instance label images (0 background, 1..N instances), seam carving (8-neighborhood) -> binary -> Analyze Particles (um^2) -> Morphology + CMG.csv
// TRACKS: ALSO treated as instance label images, seam carving (8-neighborhood) -> binary -> Analyze Particles (um^2) -> skeleton -> LSP + IMG.csv
//
// IMPORTANT CHANGE (per Jing Li):
//  - TRACKS and CELLS BOTH keep calibration (micron) so Analyze Particles "size=" is in um^2.
//  - NO forcePixelCalibration anywhere.
//
// No ROI Manager; no add/overlay; batchMode stable.
//The unit of both the tracks and cells is um^2
//Add：ForegroundArea(um^2),TotalArea(um^2)
// Even if the foreground is 0, also continue to analyze
    /**
     *  Only invert LUT (display color), not change pixel value
     */
//

import ij.IJ;
import ij.ImagePlus;
import ij.Prefs;
import ij.WindowManager;
import ij.gui.GenericDialog;
import ij.macro.Interpreter;
import ij.measure.Calibration;
import ij.plugin.PlugIn;
import ij.process.ImageProcessor;
import ij.process.ByteProcessor;
import ij.process.ShortProcessor;

import java.awt.Dimension;
import java.awt.Font;
import java.awt.Window;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.HashSet;

public class Step3_Mask_Parsing implements PlugIn {

    // ===== Defaults =====
    private static final String DEFAULT_TRACKS_SUFFIX = "TRACKS_masks.tif";
    private static final String DEFAULT_CELLS_SUFFIX  = "CELLS_masks.tif";

    // Now BOTH are interpreted in calibrated area units (e.g., um^2 if unit=micron)
    private static final String DEFAULT_TRACKS_SIZE   = "20-Infinity";
    private static final String DEFAULT_CELLS_SIZE    = "6-80";

    // ===== GUI params =====
    private String inputDirPath;
    private String tracksSuffix;
    private String cellsSuffix;

    private String tracksSize;
    private String cellsSize;

    private boolean excludeTracksBorder;
    private boolean excludeCellsBorder;

    private boolean doCarveSeamTracks;
    private boolean doCarveSeamCells;

    private boolean saveLogToFile;
    private boolean closeLogWindow;

    @Override
    public void run(String arg) {

        // ---------- load prefs ----------
        String lastDirectory   = Prefs.get("Step3_Mask_Parsing.lastDirectory", "");
        String lastTracksSuf   = Prefs.get("Step3_Mask_Parsing.tracksSuffix", DEFAULT_TRACKS_SUFFIX);
        String lastCellsSuf    = Prefs.get("Step3_Mask_Parsing.cellsSuffix",  DEFAULT_CELLS_SUFFIX);
        String lastTracksSize  = Prefs.get("Step3_Mask_Parsing.tracksSize",   DEFAULT_TRACKS_SIZE);
        String lastCellsSize   = Prefs.get("Step3_Mask_Parsing.cellsSize",    DEFAULT_CELLS_SIZE);

        boolean lastExTr       = Prefs.get("Step3_Mask_Parsing.excludeTracksBorder", true);
        boolean lastExCe       = Prefs.get("Step3_Mask_Parsing.excludeCellsBorder",  true);

        boolean lastSeamTr     = Prefs.get("Step3_Mask_Parsing.doCarveSeamTracks",   true);
        boolean lastSeamCe     = Prefs.get("Step3_Mask_Parsing.doCarveSeamCells",    true);

        boolean lastSaveLog    = Prefs.get("Step3_Mask_Parsing.saveLogToFile",       true);
        boolean lastCloseLog   = Prefs.get("Step3_Mask_Parsing.closeLogWindow",      true);

        // ---------- GUI ----------
        GenericDialog gd = new GenericDialog("Step3_Mask_Parsing (Background Batch)");
        gd.setFont(new Font("SansSerif", Font.PLAIN, 16));
        gd.setPreferredSize(new Dimension(940, 700));

        gd.addDirectoryField("Input directory", lastDirectory, 55);
        gd.addStringField("Tracks suffix", lastTracksSuf, 24);
        gd.addStringField("Cells suffix",  lastCellsSuf,  24);

        gd.addMessage("Analyze Particles size:");
        gd.addStringField("Tracks size (um^2)", lastTracksSize, 24);
        gd.addStringField("Cells  size (um^2)", lastCellsSize,  24);

        gd.addMessage("Instance seam carving (8-neighborhood):");
        gd.addCheckbox("TRACKS: carve seam between touching labels (recommended)", lastSeamTr);
        gd.addCheckbox("CELLS : carve seam between touching labels (recommended)", lastSeamCe);

        gd.addMessage("Border handling:");
        gd.addCheckbox("Exclude border-touching TRACKS", lastExTr);
        gd.addCheckbox("Exclude border-touching CELLS",  lastExCe);

        gd.addMessage("Logging:");
        gd.addCheckbox("Save log to file", lastSaveLog);
        gd.addCheckbox("Close Log window at end", lastCloseLog);

        gd.showDialog();
        if (gd.wasCanceled()) return;

        inputDirPath = gd.getNextString().trim();
        tracksSuffix = gd.getNextString().trim();
        cellsSuffix  = gd.getNextString().trim();

        tracksSize = gd.getNextString().trim();
        cellsSize  = gd.getNextString().trim();

        doCarveSeamTracks = gd.getNextBoolean();
        doCarveSeamCells  = gd.getNextBoolean();

        excludeTracksBorder= gd.getNextBoolean();
        excludeCellsBorder = gd.getNextBoolean();

        saveLogToFile  = gd.getNextBoolean();
        closeLogWindow = gd.getNextBoolean();

        if (tracksSuffix.isEmpty()) tracksSuffix = DEFAULT_TRACKS_SUFFIX;
        if (cellsSuffix.isEmpty())  cellsSuffix  = DEFAULT_CELLS_SUFFIX;
        if (tracksSize.isEmpty())   tracksSize   = DEFAULT_TRACKS_SIZE;
        if (cellsSize.isEmpty())    cellsSize    = DEFAULT_CELLS_SIZE;

        File inputDir = new File(inputDirPath);
        if (!inputDir.isDirectory()) {
            IJ.error("Invalid input directory: " + inputDirPath);
            return;
        }

        // ---------- save prefs ----------
        Prefs.set("Step3_Mask_Parsing.lastDirectory", inputDirPath);
        Prefs.set("Step3_Mask_Parsing.tracksSuffix", tracksSuffix);
        Prefs.set("Step3_Mask_Parsing.cellsSuffix",  cellsSuffix);
        Prefs.set("Step3_Mask_Parsing.tracksSize",   tracksSize);
        Prefs.set("Step3_Mask_Parsing.cellsSize",    cellsSize);

        Prefs.set("Step3_Mask_Parsing.doCarveSeamTracks", doCarveSeamTracks);
        Prefs.set("Step3_Mask_Parsing.doCarveSeamCells",  doCarveSeamCells);

        Prefs.set("Step3_Mask_Parsing.excludeTracksBorder", excludeTracksBorder);
        Prefs.set("Step3_Mask_Parsing.excludeCellsBorder",  excludeCellsBorder);

        Prefs.set("Step3_Mask_Parsing.saveLogToFile",  saveLogToFile);
        Prefs.set("Step3_Mask_Parsing.closeLogWindow", closeLogWindow);
        Prefs.savePreferences();

        // ---------- log header ----------
        SimpleDateFormat df = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
        long startTime = System.currentTimeMillis();

        IJ.log("========================================");
        IJ.log("Step3_Mask_Parsing - Run Started");
        IJ.log("Date/Time: " + df.format(new Date()));
        IJ.log("Input directory: " + inputDirPath);
        IJ.log("Tracks suffix=" + tracksSuffix + " | size(unit^2)=" + tracksSize + " | seamCarve(8N)=" + doCarveSeamTracks + " | excludeBorder=" + excludeTracksBorder);
        IJ.log("Cells  suffix=" + cellsSuffix  + " | size(unit^2)=" + cellsSize  + " | seamCarve(8N)=" + doCarveSeamCells  + " | excludeBorder=" + excludeCellsBorder);
        IJ.log("========================================");

        File ratioCsv = new File(inputDirPath, "ForegroundRatio.csv");
        File logTxt   = new File(inputDirPath, "Step3_Mask_Parsing_Log.txt");

        int nTracks = 0, nCells = 0;

        Interpreter.batchMode = true;
        try (FileWriter fwRatio = new FileWriter(ratioCsv, false)) {

            fwRatio.write("FileName,ForegroundRatio(%),ForegroundArea(um^2),TotalArea(um^2)\n");

            Deque<File> stack = new ArrayDeque<>();
            stack.push(inputDir);

            while (!stack.isEmpty()) {
                File folder = stack.pop();
                File[] files = folder.listFiles();
                if (files == null) continue;

                for (File f : files) {
                    if (f.isDirectory()) {
                        stack.push(f);
                        continue;
                    }

                    try {
                        if (f.getName().endsWith(tracksSuffix)) {
                            processTracks(f, fwRatio);
                            nTracks++;
                        } else if (f.getName().endsWith(cellsSuffix)) {
                            processCells(f);
                            nCells++;
                        }
                    } catch (Exception e) {
                        IJ.log("ERROR: " + f.getAbsolutePath());
                        IJ.handleException(e);
                    } finally {
                        closeAllImagesSilently();
                        IJ.run("Clear Results");
                    }
                }
            }

        } catch (IOException e) {
            IJ.error("Error writing ForegroundRatio.csv: " + e.getMessage());
        } finally {
            Interpreter.batchMode = false;
        }

        long elapsed = System.currentTimeMillis() - startTime;
        IJ.log("========================================");
        IJ.log("Step3_Mask_Parsing - Run Completed");
        IJ.log("Tracks processed: " + nTracks);
        IJ.log("Cells  processed: " + nCells);
        IJ.log("Elapsed: " + (elapsed / 1000.0) + " s (" + elapsed + " ms)");
        IJ.log("========================================");

        if (saveLogToFile) {
            try {
                Window logWindow = WindowManager.getWindow("Log");
                if (logWindow != null) {
                    IJ.selectWindow("Log");
                    IJ.saveAs("Text", logTxt.getAbsolutePath());
                    IJ.log("Log saved to: " + logTxt.getAbsolutePath());
                    if (closeLogWindow) IJ.run("Close");
                }
            } catch (Exception e) {
                IJ.log("Warning: failed to save/close Log window: " + e.getMessage());
            }
        }
    }

    // ======================================================
    // TRACKS (instance labels -> seam carve -> binary -> Analyze Particles (unit^2) -> skeleton)
    // ======================================================
    private void processTracks(File file, FileWriter fwRatio) throws IOException {

        IJ.log("TRACKS: " + file.getName());

        ImagePlus imp = IJ.openImage(file.getAbsolutePath());
        if (imp == null) {
            IJ.log("  Failed to open.");
            return;
        }
        if (imp.getStackSize() > 1) imp.setSlice(1);

        // Keep calibration (micron)
        Calibration cal = imp.getCalibration();
        Calibration calCopy = (cal == null) ? null : cal.copy();

        ImagePlus labelFixed = imp;
        if (doCarveSeamTracks) {
            labelFixed = carveSeamBetweenTouchingLabels8N(imp);
            if (calCopy != null) labelFixed.setCalibration(calCopy.copy());
            safeClose(imp);
        } else {
            if (calCopy != null) labelFixed.setCalibration(calCopy.copy());
        }

        ImagePlus mask0 = labelsToBinaryMask(labelFixed);
        if (calCopy != null) mask0.setCalibration(calCopy.copy());
        safeClose(labelFixed);

        if (countForeground255(mask0) == 0) {
            IJ.log("  Skip: empty mask.");
            safeClose(mask0);
            return;
        }

        IJ.run("Clear Results");
        String opts = "size=" + tracksSize + " show=Masks clear";
        if (excludeTracksBorder) opts += " exclude";

        runOnCurrent(mask0, "Analyze Particles...", opts, true);

        ImagePlus finalMask = WindowManager.getCurrentImage();
        safeClose(mask0);

        if (finalMask == null) {
            IJ.log("  WARNING: Analyze Particles did not generate mask.");
            return;
        }

        // Ensure calibration stays (Analyze Particles output may lose it depending on Fiji)
        if (calCopy != null) finalMask.setCalibration(calCopy.copy());

        runOnCurrent(finalMask, "8-bit", "", false);

        // Only invert LUT (display color), not change pixel value
        ImageProcessor ip = finalMask.getProcessor();
        ip.invertLut();
        finalMask.updateAndDraw();

        // DEBUG: save final mask before skeleton
        String debugDir  = file.getParent();
        String debugBase = stripExt(file.getName());
        IJ.saveAs(finalMask, "PNG",
                new File(debugDir, debugBase + "_track_finalMask.png").getAbsolutePath());

        // Foreground ratio (QC) - using calibrated area units
        long fgPixels = countForeground255(finalMask);
        long totalPixels = (long) finalMask.getWidth() * (long) finalMask.getHeight();
        
        // Convert pixel counts to calibrated area (um^2)
        Calibration cal2 = finalMask.getCalibration();
        double pixelArea = (cal2 != null) ? (cal2.pixelWidth * cal2.pixelHeight) : 1.0;
        double fgArea = fgPixels * pixelArea;  // Foreground area in um^2
        double totalArea = totalPixels * pixelArea;  // Total area in um^2
        
        double ratio = fgArea * 100.0 / totalArea;
        fwRatio.write(file.getName() + "," + 
                      String.format("%.4f", ratio) + "," + 
                      String.format("%.4f", fgArea) + "," + 
                      String.format("%.4f", totalArea) + "\n");
        
        // Skip skeleton analysis if no foreground
        //if (fgPixels == 0) {
            //IJ.log("  Skip: no skeletonizable object (fgArea=0).");
            //safeClose(finalMask);
            //return;
        //}

        // Skeleton + Analyze Skeleton
        int[] beforeIDs = WindowManager.getIDList();
        HashSet<Integer> before = new HashSet<>();
        if (beforeIDs != null) for (int id : beforeIDs) before.add(id);

        runOnCurrent(finalMask, "Skeletonize (2D/3D)", "", false);
        runOnCurrent(finalMask, "Analyze Skeleton (2D/3D)", "prune=[none] calculate exclude=All", false);

        ImagePlus lsp = null;
        int[] afterIDs = WindowManager.getIDList();
        if (afterIDs != null) {
            for (int id : afterIDs) {
                if (before.contains(id)) continue;
                ImagePlus tmp = WindowManager.getImage(id);
                if (tmp == null) continue;

                String title = tmp.getTitle();
                if (title != null && title.trim().equalsIgnoreCase("Longest shortest paths")) {
                    lsp = tmp;
                } else {
                    safeClose(tmp);
                }
            }
        }

        String parentDir = file.getParent();
        String baseName = stripExt(file.getName());
        

        if (lsp != null) {
            IJ.saveAs(lsp, "PNG", new File(parentDir, baseName + "_LongestShortestPaths.png").getAbsolutePath());
            safeClose(lsp);
        } else {
            IJ.log("  WARNING: No 'Longest shortest paths' image generated.");
        }

        IJ.saveAs("Results", new File(parentDir, baseName + "_IMG.csv").getAbsolutePath());
        IJ.run("Clear Results");

        safeClose(finalMask);
    }

    // ======================================================
    // CELLS (instance labels -> seam carve -> binary -> Analyze Particles (unit^2))
    // ======================================================
    private void processCells(File file) {

        IJ.log("CELLS: " + file.getName());

        ImagePlus imp = IJ.openImage(file.getAbsolutePath());
        if (imp == null) {
            IJ.log("  Failed to open.");
            return;
        }
        if (imp.getStackSize() > 1) imp.setSlice(1);

        Calibration cal = imp.getCalibration();
        Calibration calCopy = (cal == null) ? null : cal.copy();

        ImagePlus labelFixed = imp;
        if (doCarveSeamCells) {
            labelFixed = carveSeamBetweenTouchingLabels8N(imp);
            if (calCopy != null) labelFixed.setCalibration(calCopy.copy());
            safeClose(imp);
        } else {
            if (calCopy != null) labelFixed.setCalibration(calCopy.copy());
        }

        ImagePlus bin = labelsToBinaryMask(labelFixed);
        if (calCopy != null) bin.setCalibration(calCopy.copy());
        safeClose(labelFixed);

        //if (countForeground255(bin) == 0) {
            //IJ.log("  Skip: empty mask after seam carving.");
            //safeClose(bin);
            //return;
        //}

        //String parentDir2 = file.getParent();
        //String baseName2 = stripExt(file.getName());
        //IJ.saveAs(bin, "PNG", new File(parentDir2, baseName2 + "_Morphology2.png").getAbsolutePath());

        IJ.run("Clear Results");
        IJ.run("Set Measurements...", "area perimeter shape redirect=None decimal=3");

        String opts = "size=" + cellsSize + " show=[Overlay Masks] clear";
        if (excludeCellsBorder) opts += " exclude";

        runOnCurrent(bin, "Analyze Particles...", opts, true);

        ImagePlus masks = WindowManager.getCurrentImage();
        String parentDir = file.getParent();
        String baseName = stripExt(file.getName());

        if (masks != null) {
            if (calCopy != null) masks.setCalibration(calCopy.copy());
            //runOnCurrent(masks, "Convert to Mask", "", false);
            //runOnCurrent(masks, "8-bit", "", false);

            IJ.saveAs(masks, "PNG", new File(parentDir, baseName + "_Morphology.png").getAbsolutePath());
            safeClose(masks);
        } else {
            IJ.log("  WARNING: no masks image generated, saving processed binary as fallback.");
            //runOnCurrent(bin, "Convert to Mask", "", false);
            //runOnCurrent(bin, "8-bit", "", false);
            IJ.saveAs(bin, "PNG", new File(parentDir, baseName + "_Morphology.png").getAbsolutePath());
        }

        IJ.saveAs("Results", new File(parentDir, baseName + "_CMG.csv").getAbsolutePath());
        IJ.run("Clear Results");

        safeClose(bin);
    }

    // ======================================================
    // 8-neighborhood seam carving:
    // scan unique neighbor pairs: right, down, down-right, down-left
    // one-sided deletion: remove pixel belonging to larger label value
    // ======================================================
    private ImagePlus carveSeamBetweenTouchingLabels8N(ImagePlus src) {

        ImageProcessor ip = src.getProcessor();
        int w = ip.getWidth();
        int h = ip.getHeight();

        int[] lab = new int[w * h];
        for (int y = 0; y < h; y++) {
            int idx = y * w;
            for (int x = 0; x < w; x++) {
                lab[idx + x] = ip.getPixel(x, y);
            }
        }

        boolean[] seam = new boolean[w * h];

        for (int y = 0; y < h; y++) {
            int row = y * w;
            for (int x = 0; x < w; x++) {
                int i = row + x;
                int a = lab[i];
                if (a <= 0) continue;

                if (x + 1 < w) markOneSideSeam(seam, lab, i, i + 1);         // right
                if (y + 1 < h) markOneSideSeam(seam, lab, i, i + w);         // down
                if (x + 1 < w && y + 1 < h) markOneSideSeam(seam, lab, i, i + w + 1); // down-right
                if (x - 1 >= 0 && y + 1 < h) markOneSideSeam(seam, lab, i, i + w - 1); // down-left
            }
        }

        for (int k = 0; k < lab.length; k++) {
            if (seam[k]) lab[k] = 0;
        }

        short[] out = new short[w * h];
        for (int k = 0; k < out.length; k++) {
            int v = lab[k];
            if (v < 0) v = 0;
            if (v > 65535) v = 65535;
            out[k] = (short) (v & 0xffff);
        }

        ShortProcessor sp = new ShortProcessor(w, h, out, null);
        return new ImagePlus("Labels_SeamCarved_8N", sp);
    }

    private void markOneSideSeam(boolean[] seam, int[] lab, int i, int j) {
        int a = lab[i];
        int b = lab[j];
        if (a > 0 && b > 0 && a != b) {
            if (a > b) seam[i] = true;
            else seam[j] = true;
        }
    }

    private ImagePlus labelsToBinaryMask(ImagePlus labelImp) {
        ImageProcessor ip = labelImp.getProcessor();
        int w = ip.getWidth();
        int h = ip.getHeight();

        byte[] pix = new byte[w * h];
        for (int y = 0; y < h; y++) {
            int idx = y * w;
            for (int x = 0; x < w; x++) {
                int v = ip.getPixel(x, y);
                pix[idx + x] = (byte) (v > 0 ? 255 : 0);
            }
        }

        ByteProcessor bp = new ByteProcessor(w, h, pix, null);
        return new ImagePlus("BinaryFromLabels", bp);
    }

    private void runOnCurrent(ImagePlus imp, String cmd, String opt, boolean needWindow) {
        if (imp == null) {
            IJ.run(cmd, opt == null ? "" : opt);
            return;
        }
        try {
            if (needWindow && imp.getWindow() == null) imp.show();
            if (needWindow && imp.getWindow() != null) WindowManager.setCurrentWindow(imp.getWindow());
            WindowManager.setTempCurrentImage(imp);
            IJ.run(cmd, opt == null ? "" : opt);
        } finally {
            WindowManager.setTempCurrentImage(null);
        }
    }

    private void safeClose(ImagePlus imp) {
        if (imp == null) return;
        try {
            imp.setOverlay(null);
            imp.killRoi();
            imp.changes = false;
            imp.close();
        } catch (Exception ignored) {}
    }

    private void closeAllImagesSilently() {
        try {
            int[] ids = WindowManager.getIDList();
            if (ids == null) return;
            for (int id : ids) {
                ImagePlus im = WindowManager.getImage(id);
                safeClose(im);
            }
        } catch (Exception ignored) {}
    }

    private long countForeground255(ImagePlus imp) {
        if (imp == null) return 0;
        ImageProcessor ip = imp.getProcessor();
        Object pix = ip.getPixels();
        long cnt = 0;

        if (pix instanceof byte[]) {
            byte[] p = (byte[]) pix;
            for (byte b : p) if ((b & 0xff) == 255) cnt++;
        } else {
            int w = ip.getWidth(), h = ip.getHeight();
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                    if (ip.getPixel(x, y) == 255) cnt++;
        }
        return cnt;
    }

    private String stripExt(String name) {
        return name.replaceFirst("[.][^.]+$", "");
    }
}
