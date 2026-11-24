Native Windows x64 Cerebellum Designer — no Ubuntu, WSL, VM or Python installation required.

1. Download **CerebellumDesigner_Windows_x64.zip**.
2. Extract the **entire ZIP**.
3. Double-click **CerebellumDesigner.exe**. Keep `_internal` beside it.

The interface opens in your Windows browser. **Preload a profile → SZ - structure + NMDA → Load profile** loads the included SZ changes and evidence notes. The initial profile is Healthy.

Exports include structural/electrical YAML, pretransformed SWCs, HTML/PDF reports, provenance and an MPI-8 reconstruction script. Reconstruction/simulation runs separately in the matching BSB environment; it is not performed by the Windows editor. You do not need Ubuntu on the editing PC.

Saved profiles and exports are kept in `%LOCALAPPDATA%\CerebellumDesigner`. Use **Close app** to stop the local server.

Built and automatically checked on native Windows x64, including the frozen EXE, SZ preview, export, Unicode paths and shutdown. Morphology metrics are checked against the original Ubuntu engine. Network previews are proportional estimates from bundled canonical soma coordinates. The executable is unsigned; Windows ARM and every personal GPU/security configuration are not validated.
