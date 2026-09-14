# Pixel Mobile Assist

Pixel Mobile Assist is a review-first Android helper for a pixel-art
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

## Grouped-color eyedropper workflow

Use this mode for a reviewed region containing many target colors:

1. On the phone, turn off the template's single-color filter so markers for all
   target colors are visible.
2. Open Pixel Mobile Assist. Color grouping is always enabled.
3. In **Unlocked-color profile**, disable every color the current account does
   not own. Save a named profile and reuse it for that account. The profile is
   stored only in the PC browser's local storage. Each profile also remembers
   its most recently adjusted region and eyedropper location as normalized
   screen coordinates.
4. Click **Capture** to restore the profile's saved region. To change it, choose
   **Polygon**, click **Adjust region**, and click corners around the usable canvas
   in order. Add inward corners to avoid floating buttons, then click **Finish region**.
   **Undo corner** removes the last point; **Cancel** restores the previous region.
   Choose **Rectangle** to use the original drag selection. The gold outline stays
   visible, and only markers fully inside it are included.
5. Click one mini-square of any enabled/unlocked color. This teaches Pixel
   Mobile Assist the marker dimensions and detects marker-sized components for
   every enabled profile color.
6. Click **Set eyedropper**, then click the center of the game's eyedropper icon
   in the captured phone screenshot. A cyan cross shows the calibrated point.
7. Review all colored marker-sized squares and turn false detections red.
8. Pixel Mobile Assist
   samples one representative marker, places the complete matched color group,
   then switches to the next color. Before each later color, it refreshes the
   phone screen and relocates the calibrated eyedropper if the toolbar shifted.
   This uses approximately `pixels + 2 x colors` interactions instead of
   `3 x pixels` interactions.
9. Click **Queue checked pixels**. Each color uses:

   ```text
   eyedropper -> representative marker to sample -> every marker in that color
   ```

10. Watch the phone and use **STOP** immediately if the picker or viewport does
    not behave as expected.

The built-in profile catalog contains the complete 63-color game palette. Use
**Add color** if the game introduces another color. A locked color must not
remain enabled: if the game rejects the picker sample, the previous color could
otherwise be queued.

## Detection tuning

To remove an account profile, select it and click **Delete**. **Undo delete**
restores the most recently deleted profile until the dashboard is reloaded.
Deleting the last profile creates a fresh Default profile. Existing rectangular
profiles remain compatible; polygon outlines are saved per profile as well.

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
- Detection only includes colors enabled in the selected account profile.
- The selected profile restores its saved region and eyedropper calibration.
- Random delay between taps.
- Emergency stop button.
- Every detection is shown before interaction.

The program stores only the discovered local `adb.exe` path in `config.json`.
That file is excluded from Git because it contains a user-specific Windows
path. Saved browser profiles stay in browser local storage and are not committed.

## Development

### Measuring queue speed

The dashboard's **Queue timing** panel measures each normal queue without changing
its tap sequence or delay settings. Start with 30–50 reviewed pixels in one color,
then try several colors to measure switching overhead. Results reset on Capture
or a new queue; copy them before starting another run.

- **Placement ADB**: time spent executing each placement command, including PC
  process startup, communication and Android command execution.
- **Random wait (actual)**: measured waiting time, which can exceed the requested
  delay because of operating-system scheduling. STOP can shorten a wait.
- **Eyedropper press / Color sample ADB**: commands used to select each color.
- **Screenshot / Icon matching**: relocation work between color groups.
- **Overall**: completed placement commands divided by elapsed queue time.

Each category shows its average, maximum, count and total duration. A final JSON
summary prefixed with `Queue timing:` is printed in the terminal on completion,
STOP or error. Failed commands are included in the corresponding timing bucket
and marked as failures. These measurements do not verify that the game accepted
each tap, or isolate USB time from Android input-command time.

Run the tests from the project directory:

```powershell
py -m unittest discover -s tests -v
```

The project is intended only for uses permitted by the relevant service and
account rules. Review detected candidates before queueing changes.
