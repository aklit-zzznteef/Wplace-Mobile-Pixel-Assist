# Pixel Mobile Assist

Pixel Mobile Assist is a review-first Android helper for a filtered pixel-art
template. It opens a local dashboard in your normal browser, detects the small
squares that mark incorrect pixels, and queues reviewed taps through ADB.

## First-time setup

Requirements:

- Windows with Python 3.11 or newer
- USB debugging enabled and authorized
- scrcpy/ADB working
- The game open on the phone with the template visible

Install the dependencies once:

```powershell
py -m pip install -r requirements.txt
```

You can also right-click `setup.ps1` and run it with PowerShell. Then
double-click:

```text
run.cmd
```

On the development PC, the launcher can use Codex's bundled Python runtime. On
other PCs it uses `py` or `python`. Keep the terminal window that opens running.
If startup fails, it remains open and shows the reason. Check that the phone is
connected, unlocked, and has authorized USB debugging. Also close any older
Pixel Mobile Assist window because only one can use the default port (`8765`).

If you later install your own Python, the equivalent commands are:

```powershell
py -m pip install -r requirements.txt
py pixel_assist.py
```

Keep the PowerShell window open while using the dashboard. The local server is
available only from your own PC (`127.0.0.1`) and uses a random session token.

Pixel Mobile Assist searches common scrcpy folders under Downloads for
`adb.exe`. You can supply it explicitly if needed:

```text
run.cmd --adb "C:\path\to\scrcpy\adb.exe"
```

## Mono filtered workflow

1. On the phone, zoom to the area you want to work on.
2. Select an **unlocked** palette colour.
3. Enable the template filter so only that target colour is shown.
4. Do not pan or zoom while Pixel Mobile Assist is reviewing or queueing.
5. Click **Capture**. A fixed gold canvas region appears automatically below the
   floating top controls and extends downward toward the paint/palette panel.
   Use **Adjust region** only when you want to replace the automatic rectangle;
   releasing the new rectangle immediately enters sampling mode.
6. Pixel Mobile Assist immediately enters sampling mode. Click inside one small
   wrong-pixel square.
7. Review the outlined candidate squares:
   - Green candidates will be tapped.
   - Click a candidate to turn it red and exclude it.
8. Click **Queue checked pixels**. The reviewed queue starts immediately without
   a confirmation pop-up or pixel-count limit.
9. Watch the phone. Press **STOP** if anything looks wrong.
10. When queueing ends, inspect all pending pixels and press **Paint yourself**
    only if the selection is correct.

After painting, pan or zoom as needed and begin again with a new capture.

## Mixed-color eyedropper workflow

Use this mode for a reviewed region containing many target colors:

1. On the phone, turn off the template's single-color filter so markers for all
   target colors are visible.
2. In Pixel Mobile Assist, choose **Mixed eyedropper**.
3. In **Unlocked-color profile**, disable every color the current account does
   not own. Save a named profile and reuse it for that account. The profile is
   stored only in the PC browser's local storage. Each profile also remembers
   its most recently adjusted region and eyedropper location as normalized
   screen coordinates.
4. Click **Capture** and optionally use **Adjust region**.
5. Click one mini-square of any enabled/unlocked color. This teaches Pixel
   Mobile Assist the marker dimensions and detects marker-sized components for
   every enabled profile color.
6. Click **Set eyedropper**, then click the center of the game's eyedropper icon
   in the captured phone screenshot. A cyan cross shows the calibrated point.
7. Review all colored marker-sized squares and turn false detections red.
8. Leave **Group same colors** enabled for the faster workflow. Pixel Mobile Assist
   samples one representative marker, places the complete matched color group,
   then switches to the next color. Before each later color, it refreshes the
   phone screen and relocates the calibrated eyedropper if the toolbar shifted.
   This uses approximately `pixels + 2 x colors` interactions instead of
   `3 x pixels` interactions.
9. Click **Queue checked pixels**. In grouped mode, each color uses:

   ```text
   eyedropper -> representative marker to sample -> every marker in that color
   ```

   Turn grouping off to use the slower eyedropper/sample/place sequence for
   every individual pixel.
10. Watch the phone and use **STOP** immediately if the picker or viewport does
    not behave as expected.

### Dimensions-only eyedropper

Enable **Dimensions-only eyedropper (ignore all colors)** inside Mixed mode when
you want every sampled-size marker processed independently. It does not consult
the selected profile, the built-in palette, or any list of expected colors.
Instead, it discovers all visible solid-color connected components and retains
only components whose dimensions, area, and aspect ratio match the sampled
mini-square. Grouping is disabled and each candidate uses:

```text
eyedropper -> candidate marker to sample -> candidate marker to place
```

Review the preview carefully. If adjacent same-color marker interiors touch in
the screenshot, they form one connected shape and can be rejected for having
the wrong dimensions.

The built-in profile catalog contains the complete 63-color game palette. Use
**Add color** if the game introduces another color. A locked color must not
remain enabled: if the game rejects the picker sample, the previous color could
otherwise be queued.

## Detection tuning

- **Colour tolerance** defaults to 5. Increase it slightly if browser rendering
  creates minor colour variations. Lower it if unrelated pixels are detected.
- Candidate dimensions and area must remain within 35% of the sampled
  mini-square; larger full-size pixels and shapes wider than a 1.6:1 aspect
  ratio are rejected.
- **Random delay** defaults to 0.01-0.08 seconds between every action.
- Always sample the solid interior of a mini-square, not its edge.
- Verify that the fixed gold rectangle contains only canvas. If the phone UI
  layout changes, adjust the fixed region in the project before queueing.
- If the filtered colour has no visible wrong-pixel marker, move to another area
  and capture again.

## Safety behavior

- Valid reviewed queues start immediately with no pixel-count limit.
- Profile-filtered mixed mode only detects colors enabled in the selected
  account profile. Dimensions-only mode deliberately ignores that profile.
- Mixed mode restores the selected profile's saved eyedropper calibration.
- Random delay between taps.
- Emergency stop button.
- Every detection is shown before interaction.

The program stores only the discovered local `adb.exe` path in `config.json`.
That file is excluded from Git because it contains a user-specific Windows
path. Saved browser profiles stay in browser local storage and are not committed.

## Development

Run the tests from the project directory:

```powershell
py -m unittest discover -s tests -v
```

The project is intended only for uses permitted by the relevant service and
account rules. Review detected candidates before queueing changes.
