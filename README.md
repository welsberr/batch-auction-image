# Batch Auction Image

A local proof of concept for reviewing, renaming, and cropping auction photographs in batches. It proposes groupings and crops, provides a browser review, and creates new output files while leaving the originals in place. Human review is essential: the tool cannot reliably identify a can's front, seam, top, or bottom, and a crop or grouping can be wrong even without a warning.

## Windows: install and run

1. Install Python 3.10 or later for Windows with the Python launcher and Tk support. Download it from [python.org](https://www.python.org/downloads/windows/).
2. Download this repository as a ZIP from GitHub and extract it to a writable folder, or clone it with Git. Keep the application files together. Do not run it inside the ZIP.
3. Double-click `INSTALL.bat`. It creates `.venv` if needed and downloads the required packages from the Python package index; internet access is needed for this step.
4. Double-click `RUN.bat`. Keep the application and its console window open while using the browser review or creating output.

The Windows installer and desktop interface have not yet been validated on every Windows configuration. If installation fails, read the console output. This repository does not include an offline Python installer or package wheels.

## Finish from an existing reviewed plan

The desktop app can process an existing `reviewed-plan*.json` directly, even if the original review page is unavailable:

1. In **Create copies after review**, use **Choose** to select the saved JSON plan.
2. Choose a parent folder for output. The app proposes a new output folder. It must be outside the original photos folder and must not already exist.
3. Choose **Cropped, contrast-adjusted JPEGs** and click **Create reviewed copies**. The app applies the saved crop, contrast, and size settings. Choose the PaintShop Pro option instead for byte-identical renamed copies with no crop, contrast, or resizing.
4. Check the completion message, the output images, `processing-report.csv`, and `mapping.csv` before uploading. Per-photo errors are reported and other eligible images continue. If retrying, use a new output folder.

Version 1 plans from the earlier application remain supported, including older full plans without a `plan_kind` field. The processor uses only included and reviewed records. Saved plans contain original absolute file paths and hashes: the original photos need to be available at those paths and unchanged. A plan alone does not contain the photos, and moving the source folder to another computer or path is not automatically handled. Keep saved plans and photos private; do not commit them to GitHub.

## Analyze and review a new batch

Choose the original photos, a new review folder, the auction number, starting can number, and either two- or six-photo mode. Click **Analyze photos and open review**. In the browser, check every included photo's number, view letter, crop, and warnings. New photos start with Include and Reviewed checked; the checkmarks are not a guarantee of correctness. Use **Save work in progress** to preserve unfinished decisions and **Download reviewed plan** to save included, reviewed photos for output.

For two views, `a` means front and `b` is the seam; for six, `a` through `f` mean face, right, back, left, top, and bottom. Letters are suggestions based on sequence, not recognition of these features. Check the actual image. Focus warnings are provisional and can miss blur or flag smooth subjects. The detector assumes a contrasting background; crop detection may fail silently. Review the output before use.

When the review was opened from the desktop app, saving a reviewed plan enables **Create output images**. Select it and choose an output parent folder in the desktop app. The exact plan used is saved as `reviewed-plan-used.json` in the output. Changing review settings disables the button until the plan is saved again. A reviewed plan contains only included, reviewed photos; use a work-in-progress file to retain excluded and unfinished decisions.

To bring an older review page forward, first save any unsaved decisions in the old page. In the updated desktop app choose **Update/open existing review**, select the old HTML, then load the matching saved plan in the newly opened page. Existing reviews and photos are not reanalyzed or overwritten. If only the JSON is available, use the direct desktop workflow above.

## Updating an existing installation

Save any work in an open browser review and let active processing finish. Download the latest repository ZIP, extract it, and copy the application files into the existing installation folder, replacing same-named application files. Keep the existing `.venv`, photos, review folders, JSON plans, and outputs. Start `RUN.bat` from the existing installation; the old desktop launcher remains compatible. If dependencies need installing, run `INSTALL.bat` from that folder. Installing the repository does not require committing or uploading project files.

Private GitHub repositories require each recipient to have access before they can download an update. The application uses a local loopback connection between its browser page and desktop app; no photos are uploaded by the app.

## Development and verification

Install the dependencies in `requirements.txt`, then run:

```text
python test_poc.py
python test_legacy_plan.py
python test_batch_continuation.py
python test_review_server.py
python test_desktop_output.py
node test_review_ui.js
```

`test_review_server.py` opens a loopback port and may require permission in a sandbox. The tests use synthetic data. Desktop dialogs are mocked in the desktop test; real Windows and PaintShop Pro integration still require validation. Crop mode re-encodes JPEGs and can alter appearance; full-range contrast stretches RGB channels independently. Preview and inspect representative images before processing or publishing a batch.
