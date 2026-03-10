// Version: Java conversion from BeanShell script
// Supports file paths containing spaces
// Supports processing both two-channel and three-channel images
// Automatically saves outputs based on channel color/labels
// New: automatic contrast adjustment (compute min/max using percentile-based clipping
//      to better match human visual perception)
// Retained: manual min/max settings (used as a fallback)


import ij.IJ;
import ij.ImagePlus;
import ij.Prefs;
import ij.gui.GenericDialog;
import ij.io.FileSaver;
import ij.measure.Calibration;
import ij.process.ImageConverter;
import ij.process.ImageProcessor;
import ij.process.ImageStatistics;
import ij.process.LUT;
import ij.plugin.PlugIn;

import loci.formats.ImageReader;
import loci.formats.FormatException;
import loci.plugins.BF;
import loci.plugins.in.ImporterOptions;

import java.awt.Dimension;
import java.awt.Font;
import java.io.File;
import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashMap;
import java.util.Stack;

public class Step1_SplitChannelsByColor implements PlugIn {

    private String fileExtension;
    private String cellsColor;   // Color assigned to CELLS (Red, Green, or Blue)
    private String tracksColor;  // Color assigned to TRACKS (Red, Green, or Blue)

    // Auto-contrast settings
    private boolean useAutoContrast = true;
    private double satLowPercent = 0.1;   // e.g. 0.1 means 0.1% pixels saturated at low end
    private double satHighPercent = 0.1;  // e.g. 0.1 means 0.1% pixels saturated at high end
    
    // Manual min/max values for each color channel
    private double redMin = 0;
    private double redMax = 1500;
    private double greenMin = 0;
    private double greenMax = 500;
    private double blueMin = 0;
    private double blueMax = 5000;
    
    // Image processing options
    private boolean resizeTo512 = true;
    private boolean convertTo8bit = true;

    @Override
    public void run(String arg) {
        HashMap<String, String> params = new HashMap<>();

        // Load last preferences
        String lastDirectory = Prefs.get("Step1_SplitChannelsByColor.lastDirectory", "");
        String lastCellsColor = Prefs.get("Step1_SplitChannelsByColor.cellsColor", "Red");
        String lastTracksColor = Prefs.get("Step1_SplitChannelsByColor.tracksColor", "Green");
        String lastExt = Prefs.get("Step1_SplitChannelsByColor.ext", ".czi");
        
        // Default values - CHANGE THESE to update GUI defaults
        // These values are always used (not saved/loaded from Preferences)
        boolean defaultAutoContrast = true;
        double defaultSatLow = 0.1;
        double defaultSatHigh = 0.1;
        
        double defaultRedMin = 0.0;
        double defaultRedMax = 1500.0;
        double defaultGreenMin = 0.0;
        double defaultGreenMax = 500.0;
        double defaultBlueMin = 0.0;
        double defaultBlueMax = 5000.0;
        
        boolean defaultResizeTo512 = true;
        boolean defaultConvertTo8bit = true;

        // Prompt user for inputs
        GenericDialog gd = new GenericDialog("Split Channels By Color - Parameters");
        Font font = new Font("SansSerif", Font.PLAIN, 16);
        gd.setFont(font);
        gd.setPreferredSize(new Dimension(680, 680));

        gd.addDirectoryField("Input directory", lastDirectory, 35);
        gd.addStringField("Input file extension", lastExt, 20);

        String[] colorOptions = {"Red", "Green", "Blue"};
        gd.addChoice("CELLS color", colorOptions, lastCellsColor);
        gd.addChoice("TRACKS color", colorOptions, lastTracksColor);

        gd.addMessage("Contrast / Display settings (for visibility only):");
        gd.addCheckbox("Auto contrast (percentile stretch)", defaultAutoContrast);
        gd.addNumericField("Low saturation (%)", defaultSatLow, 3);   // 0.1 means 0.1%
        gd.addNumericField("High saturation (%)", defaultSatHigh, 3); // 0.1 means 0.1%
        
        gd.addMessage("Manual min/max values (used when auto contrast is disabled):");
        gd.addNumericField("Red   Min:", defaultRedMin, 0);
        gd.addNumericField("      Max:", defaultRedMax, 0);
        gd.addNumericField("Green Min:", defaultGreenMin, 0);
        gd.addNumericField("      Max:", defaultGreenMax, 0);
        gd.addNumericField("Blue  Min:", defaultBlueMin, 0);
        gd.addNumericField("      Max:", defaultBlueMax, 0);
        
        gd.addMessage("Image processing options:");
        gd.addCheckbox("Resize to 512x512", defaultResizeTo512);
        gd.addCheckbox("Convert to 8-bit", defaultConvertTo8bit);

        gd.showDialog();
        if (gd.wasCanceled()) return;

        String inputDirPath = gd.getNextString();
        fileExtension = gd.getNextString();
        cellsColor = gd.getNextChoice();
        tracksColor = gd.getNextChoice();

        useAutoContrast = gd.getNextBoolean();
        satLowPercent = gd.getNextNumber();
        satHighPercent = gd.getNextNumber();
        
        // Read min/max values for each color
        redMin = gd.getNextNumber();
        redMax = gd.getNextNumber();
        greenMin = gd.getNextNumber();
        greenMax = gd.getNextNumber();
        blueMin = gd.getNextNumber();
        blueMax = gd.getNextNumber();
        
        resizeTo512 = gd.getNextBoolean();
        convertTo8bit = gd.getNextBoolean();

        // Basic sanity checks
        if (fileExtension == null || fileExtension.trim().isEmpty()) fileExtension = ".czi";
        if (!fileExtension.startsWith(".")) fileExtension = "." + fileExtension;

        if (satLowPercent < 0) satLowPercent = 0;
        if (satHighPercent < 0) satHighPercent = 0;
        if (satLowPercent > 20) satLowPercent = 20;
        if (satHighPercent > 20) satHighPercent = 20;
        
        // Validate min/max values
        if (redMin < 0) redMin = 0;
        if (greenMin < 0) greenMin = 0;
        if (blueMin < 0) blueMin = 0;
        if (redMax <= redMin) redMax = redMin + 1;
        if (greenMax <= greenMin) greenMax = greenMin + 1;
        if (blueMax <= blueMin) blueMax = blueMin + 1;

        // Save preferences
        Prefs.set("Step1_SplitChannelsByColor.lastDirectory", inputDirPath);
        Prefs.set("Step1_SplitChannelsByColor.ext", fileExtension);
        Prefs.set("Step1_SplitChannelsByColor.cellsColor", cellsColor);
        Prefs.set("Step1_SplitChannelsByColor.tracksColor", tracksColor);
        Prefs.savePreferences();

        // Record start time and date
        SimpleDateFormat dateFormat = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
        String startDateTime = dateFormat.format(new Date());
        long startTime = System.currentTimeMillis();
        
        // Log all parameters at the start
        IJ.log("========================================");
        IJ.log("Split Channels By Color - Run Started");
        IJ.log("Date and Time: " + startDateTime);
        IJ.log("========================================");
        IJ.log("INPUT SETTINGS:");
        IJ.log("  Input directory: " + inputDirPath);
        IJ.log("  File extension: " + fileExtension);
        IJ.log("");
        IJ.log("COLOR MAPPING:");
        IJ.log("  CELLS color: " + cellsColor);
        IJ.log("  TRACKS color: " + tracksColor);
        IJ.log("");
        IJ.log("CONTRAST SETTINGS:");
        IJ.log("  Auto contrast: " + useAutoContrast);
        if (useAutoContrast) {
            IJ.log("  Low saturation (%): " + satLowPercent);
            IJ.log("  High saturation (%): " + satHighPercent);
        } else {
            IJ.log("  Manual min/max values (from GUI):");
            IJ.log("    Red:   [" + redMin + ", " + redMax + "]");
            IJ.log("    Green: [" + greenMin + ", " + greenMax + "]");
            IJ.log("    Blue:  [" + blueMin + ", " + blueMax + "]");
        }
        IJ.log("");
        IJ.log("IMAGE PROCESSING OPTIONS:");
        IJ.log("  Resize to 512x512: " + resizeTo512);
        IJ.log("  Convert to 8-bit: " + convertTo8bit);
        IJ.log("========================================");
        IJ.log("");

        File inputDir = new File(inputDirPath);
        if (!inputDir.isDirectory()) {
            IJ.log("Invalid input folder.");
            return;
        }

        // Use Stack for folder traversal
        Stack<File> stack = new Stack<>();
        stack.push(inputDir);

        while (!stack.isEmpty()) {
            File current = stack.pop();
            File[] files = current.listFiles();
            if (files == null) continue;

            for (File file : files) {
                if (file.isDirectory()) {
                    stack.push(file);
                } else if (file.getName().endsWith(fileExtension)) {
                    try {
                        processFile(file);
                    } catch (Exception e) {
                        IJ.log("Error processing file: " + file.getName() + " — " + e.getMessage());
                        e.printStackTrace();
                    }
                }
            }
        }

        long elapsed = System.currentTimeMillis() - startTime;
        String endDateTime = dateFormat.format(new Date());
        double elapsedSeconds = elapsed / 1000.0;
        
        // Log summary at the end (parameters already logged at start)
        IJ.log("");
        IJ.log("========================================");
        IJ.log("Split Channels By Color - Run Completed");
        IJ.log("End Date and Time: " + endDateTime);
        IJ.log("Processing Time: " + elapsedSeconds + " seconds (" + elapsed + " ms)");
        IJ.log("========================================");

        // Save log
        try {
            IJ.log("");
            IJ.log("---- Saving log to file ----");
            IJ.selectWindow("Log");
            IJ.saveAs("Text", inputDirPath + File.separator + "Step1_SplitChannelsByColor.txt");
            IJ.log("Log saved to: " + inputDirPath + File.separator + "Step1_SplitChannelsByColor.txt");
            IJ.selectWindow("Log");
            IJ.run("Close");
        } catch (Exception e) {
            IJ.log("Warning: failed to save/close Log window: " + e.getMessage());
        }
    }

    /**
     * Process a single file: split channels, detect colors, and save
     */
    private void processFile(File file) {
        String path = file.getAbsolutePath().replace("\\", "/");
        IJ.log("Processing: " + path);

        // Get series count
        int seriesCount = 1;
        try {
            ImageReader reader = new ImageReader();
            reader.setId(path);
            seriesCount = reader.getSeriesCount();
            reader.close();
        } catch (Exception e) {
            IJ.log("Warning: failed to get series count, default 1.");
        }

        // Process each series
        for (int s = 0; s < seriesCount; s++) {
            try {
                ImporterOptions opt2 = new ImporterOptions();
                opt2.setId(path);
                opt2.setSeriesOn(s, true);
                opt2.setSplitChannels(true);
                opt2.setColorMode(ImporterOptions.COLOR_MODE_DEFAULT);
                opt2.setStackOrder(ImporterOptions.ORDER_XYCZT);

                ImagePlus[] imps = BF.openImagePlus(opt2);
                if (imps == null || imps.length == 0) continue;
                int nChannels = imps.length;

                // Process each channel
                for (int c = 0; c < nChannels; c++) {
                    ImagePlus chImp = imps[c];
                    String labelOrColor = getChannelColorName(chImp, c); // "_CELLS" / "_TRACKS" / "Red" / "Ch1" etc.

                    ImagePlus processed;
                    int targetW = resizeTo512 ? 512 : chImp.getWidth();
                    int targetH = resizeTo512 ? 512 : chImp.getHeight();
                    
                    if (useAutoContrast) {
                        // Optional: you can customize sat% based on label
                        double low = satLowPercent;
                        double high = satHighPercent;

                        // Example: TRACKS often has sparse bright tracks; slightly higher high-sat can avoid over-bright
                        if ("_TRACKS".equals(labelOrColor)) {
                            high = Math.max(high, 0.3);
                        }
                        processed = preprocessAuto(chImp, targetW, targetH, low / 100.0, high / 100.0);
                    } else {
                        double[] mm = getMinMaxByColor(labelOrColor);
                        IJ.log("  Channel " + labelOrColor + " using min/max: [" + mm[0] + ", " + mm[1] + "]");
                        processed = preprocessManual(chImp, targetW, targetH, mm[0], mm[1]);
                    }

                    String parentDir = file.getParent();
                    String baseName = file.getName().replaceFirst("[.][^.]+$", "");
                    String savePath = parentDir + File.separator + baseName + "_S" + (s + 1) + labelOrColor + ".tif";

                    new FileSaver(processed).saveAsTiff(savePath);
                    IJ.log("Saved: " + savePath);

                    // Close
                    processed.close();
                    chImp.close();
                }
            } catch (IOException e) {
                IJ.log("IO Error processing series " + (s + 1) + " of file " + file.getName() + ": " + e.getMessage());
            } catch (FormatException e) {
                IJ.log("Format Error processing series " + (s + 1) + " of file " + file.getName() + ": " + e.getMessage());
            } catch (Exception e) {
                IJ.log("Error processing series " + (s + 1) + " of file " + file.getName() + ": " + e.getMessage());
            }
        }
    }

    /**
     * Manual preprocess: set fixed display range, optionally resize, optionally convert to 8-bit
     */
    private ImagePlus preprocessManual(ImagePlus imp, int targetW, int targetH, double min, double max) {
        if (imp == null) return null;

        imp.setDisplayRange(min, max);
        imp.updateAndDraw();

        if (resizeTo512) {
            int width = imp.getWidth();
            int height = imp.getHeight();

            ImageProcessor ip = imp.getProcessor().resize(targetW, targetH);

            Calibration cal = imp.getCalibration();
            cal.pixelWidth *= (width / (double) targetW);
            cal.pixelHeight *= (height / (double) targetH);
            imp.setCalibration(cal);
            imp.setProcessor(ip);
        }

        if (convertTo8bit) {
            ImageConverter.setDoScaling(true);
            IJ.run(imp, "8-bit", "");
        }
        return imp;
    }

    /**
     * Auto preprocess: compute display min/max by histogram percentiles, optionally resize, optionally convert to 8-bit
     * satLow/satHigh are fractions (e.g. 0.001 = 0.1%)
     */
    private ImagePlus preprocessAuto(ImagePlus imp, int targetW, int targetH, double satLow, double satHigh) {
        if (imp == null) return null;

        double[] mm = autoMinMaxByPercentile(imp, satLow, satHigh);
        double min = mm[0], max = mm[1];

        imp.setDisplayRange(min, max);
        imp.updateAndDraw();

        if (resizeTo512) {
            int width = imp.getWidth();
            int height = imp.getHeight();

            ImageProcessor ip = imp.getProcessor().resize(targetW, targetH);

            Calibration cal = imp.getCalibration();
            cal.pixelWidth *= (width / (double) targetW);
            cal.pixelHeight *= (height / (double) targetH);
            imp.setCalibration(cal);
            imp.setProcessor(ip);
        }

        if (convertTo8bit) {
            ImageConverter.setDoScaling(true);
            IJ.run(imp, "8-bit", "");
        }
        return imp;
    }

    /**
     * Auto compute display min/max by histogram percentiles.
     * satLow/satHigh are fractions (e.g., 0.001 = 0.1%).
     *
     * Notes:
     * - This is for visualization/8-bit scaling, not for quantitative analysis.
     * - Uses histogram-based percentile approximation (fast).
     */
    private double[] autoMinMaxByPercentile(ImagePlus imp, double satLow, double satHigh) {
        ImageProcessor ip = imp.getProcessor();
        
        // Get min/max values
        ImageStatistics stats = ImageStatistics.getStatistics(
                ip,
                ij.measure.Measurements.MIN_MAX,
                null
        );
        
        double dataMin = stats.min;
        double dataMax = stats.max;
        
        // Get histogram directly from ImageProcessor
        int[] hist = ip.getHistogram();
        if (hist == null || hist.length == 0) {
            return new double[]{dataMin, dataMax};
        }

        long total = 0;
        for (int h : hist) total += h;
        if (total <= 0) return new double[]{dataMin, dataMax};

        // Clamp saturation percentages
        if (satLow < 0) satLow = 0;
        if (satHigh < 0) satHigh = 0;
        if (satLow > 0.5) satLow = 0.5;
        if (satHigh > 0.5) satHigh = 0.5;

        long lowTarget = Math.round(total * satLow);
        long highTarget = Math.round(total * (1.0 - satHigh));

        int bins = hist.length;
        double binWidth = (dataMax - dataMin) / bins;

        // Find low bin (percentile from low end)
        long cum = 0;
        int lowBin = 0;
        for (int i = 0; i < bins; i++) {
            cum += hist[i];
            if (cum >= lowTarget) { 
                lowBin = i; 
                break; 
            }
        }

        // Find high bin (percentile from high end)
        cum = 0;
        int highBin = bins - 1;
        for (int i = 0; i < bins; i++) {
            cum += hist[i];
            if (cum >= highTarget) { 
                highBin = i; 
                break; 
            }
        }

        double min = dataMin + lowBin * binWidth;
        double max = dataMin + (highBin + 1) * binWidth;

        // Safety fallback
        if (Double.isNaN(min) || Double.isNaN(max) || max <= min) {
            min = dataMin;
            max = dataMax;
        }
        return new double[]{min, max};
    }

    /**
     * Get channel color name based on LUT and user's color mapping
     * Return values used in filename suffix:
     * - "_CELLS" or "_TRACKS" if detected color matches mapping
     * - "Red"/"Green"/"Blue" if detected but not mapped
     * - "ChX" if unknown LUT
     */
    private String getChannelColorName(ImagePlus imp, int channelIndex) {
        LUT lut = imp.getProcessor().getLut();
        int r = lut.getRed(255);
        int g = lut.getGreen(255);
        int b = lut.getBlue(255);

        String detectedColor;
        if (r == 255 && g == 0 && b == 0) {
            detectedColor = "Red";
        } else if (r == 0 && g == 255 && b == 0) {
            detectedColor = "Green";
        } else if (r == 0 && g == 0 && b == 255) {
            detectedColor = "Blue";
        } else {
            return "_Ch" + (channelIndex + 1); // fallback for unknown colors
        }

        // Map detected color to user-defined labels
        if (detectedColor.equals(cellsColor)) {
            return "_CELLS";
        } else if (detectedColor.equals(tracksColor)) {
            return "_TRACKS";
        } else {
            return "_" + detectedColor; // keep consistent suffix style
        }
    }

    /**
     * Get min/max values based on label/color name (manual mode)
     * Dynamically uses the color assigned to CELLS/TRACKS by the user
     */
    private double[] getMinMaxByColor(String colorName) {
        // If it's a mapped label, use the color assigned by user
        if (colorName.equals("_CELLS")) {
            return getMinMaxByColorName(cellsColor);
        }
        if (colorName.equals("_TRACKS")) {
            return getMinMaxByColorName(tracksColor);
        }

        // For unmapped colors, extract color name (remove leading underscore if present)
        String color = colorName.startsWith("_") ? colorName.substring(1) : colorName;
        return getMinMaxByColorName(color);
    }

    /**
     * Get min/max values for a specific color (Red, Green, or Blue)
     * Uses user-defined values from GUI
     */
    private double[] getMinMaxByColorName(String color) {
        if (color == null) {
            return new double[]{0, 65535};
        }
        
        if (color.equals("Red")) {
            return new double[]{redMin, redMax};
        } else if (color.equals("Green")) {
            return new double[]{greenMin, greenMax};
        } else if (color.equals("Blue")) {
            return new double[]{blueMin, blueMax};
        }
        
        // Default for unknown colors
        return new double[]{0, 65535};
    }
}


