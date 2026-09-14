# Pixel Mobile Assist

An Android pixel-placement helper that runs on your Windows PC. It detects
small template markers and queues pixels through ADB, completing one color
before moving to the next.

## Setup

You need Python 3.11+, ADB (included with scrcpy), and an Android phone connected
by USB with USB debugging authorized.

Open a terminal in the project folder and install the dependencies:

```powershell
py -m pip install -r requirements.txt
```

Double-click **run.cmd** to open the dashboard. Keep its terminal window open.

If ADB isn't found, specify its location:

```text
run.cmd --adb "C:\path\to\scrcpy\adb.exe"
```

## How to use

1. Open the game and template on your phone. Show all template colors and zoom
   into the area you want to complete.
2. Choose or save a profile containing only colors your account has unlocked.
3. Click **Capture**. Use **Adjust region** if needed: drag a rectangle, or
   choose **Polygon**, click corners around the canvas, and click **Finish region**.
   Avoid including game buttons.
4. Click inside a small incorrect-pixel marker to detect matching markers.
5. Click **Set eyedropper**, then select the game's eyedropper button in the
   screenshot. Reuse the saved position if it is still correct.
6. Review the outlined pixels. Click any unwanted candidate to exclude it.
7. Click **Queue checked pixels**. Keep the phone view still while it runs;
   **STOP** ends the queue.
8. Review the result on your phone and press **Paint** when ready.

Capture again after panning or zooming.

## Settings and profiles

- **Tolerance:** defaults to 5. Increase slightly for missed colors; decrease
  if unrelated colors are detected.
- **Delay:** defaults to 0.01–0.08 seconds of extra waiting between actions.
- **Profiles:** remember colors, region shape, and eyedropper position in your
  PC browser. **Delete** removes a profile; **Undo delete** restores the last
  deletion until you reload.
- **Queue timing:** shows command speed and where queue time is spent.

If startup fails, read the terminal error. Check the USB connection and debugging
authorization, and close any older app instance using the same port.

## Development

Run tests from the project folder:

```powershell
py -m unittest discover -s tests -v
```
