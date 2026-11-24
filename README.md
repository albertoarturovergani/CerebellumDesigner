# Cerebellum Designer

**Version 0.0.1 — maintained by Alberto Arturo Vergani.**

CD transforms morphological, network and electrical features of the cerebellar network relative to the canonical model.

This repository distributes the verified **Ubuntu 24.04 LTS installation kit** and a **Windows launcher using WSL2** for Cerebellum Designer, BSB 8.0.2 and cerebellar-models 0.13.0. The kit includes readable application source code, model source, configuration files and installation scripts. It does not contain Python environments or simulation results.

## Download and install

### Windows (WSL2)

1. [Download the Windows package](downloads/CerebellumDesigner_Windows_WSL2_20261124.zip?raw=true) and extract the entire ZIP into a local Windows folder.
2. If needed, install WSL2 and Ubuntu 24.04 from an Administrator PowerShell: `wsl --install -d Ubuntu-24.04`. Restart if requested, then open Ubuntu once to create your Linux username/password.
3. Double-click **`1_Install_Designer.cmd`** as a normal Windows user. Wait for installation to finish.
4. Double-click **`2_Start_Designer.cmd`**. The dashboard opens in your **Windows browser**.

**`3_Open_Exports.cmd`** opens your generated files in Explorer. **`4_Reconstruction_Terminal.cmd`** opens a Linux terminal with the BSB environment activated; reconstruction remains an explicit action with `bash reconstruct.sh` and **MPI-8**.

The Windows package runs the same pinned Ubuntu backend through WSL2; it is **not a native standalone Windows executable**. It targets x64 and does not alter an existing VirtualBox/VMware Ubuntu VM. The scientific source and presets are unchanged. Files live under `~/CerebellumDesigner_WSL` in the selected WSL distribution. Keep that folder and your WSL distribution to retain saved work. The launchers do not change global PowerShell policy or open firewall ports. Windows ARM and full end-to-end installation on a physical Windows/WSL2 machine have not been validated.

[Windows instructions in Italian](windows/README_IT.txt) · [Launcher source](windows/) · [Checksums](downloads/SHA256SUMS)

### Ubuntu / Ubuntu VM

1. Open this page in the browser **inside your Ubuntu VM**.
2. [Download the Ubuntu installation kit](downloads/CerebellumDesigner_Ubuntu_20261123.tar.gz?raw=true).
3. Extract the archive into your Ubuntu Home folder. The extracted directory should be `~/CerebellumDesigner_Ubuntu`.
4. In an Ubuntu terminal, run:

```bash
cd ~/CerebellumDesigner_Ubuntu
bash setup_ubuntu.sh
bash start_designer.sh
```

Then open **http://127.0.0.1:8891/** in the browser inside Ubuntu. Keep the terminal open; Ctrl+C stops the server.

The installer requests `sudo` only for Ubuntu packages and creates a local Python environment named `szpaper2`. Run it as your normal Ubuntu user, not with `sudo bash`. Internet access is needed for apt and pip. The application binds only to loopback.

[Full installation instructions in Italian](docs/INSTALL_UBUNTU_IT.txt) · [SHA-256 checksum](downloads/SHA256SUMS)

## Configure and reconstruct

- **Cells:** morphology size, rotation, bifurcation tilt and intrinsic electrical parameters.
- **Network:** layer thickness, population density and pathway-specific electrical parameters.
- **Review & save:** YAML, pretransformed SWCs, HTML/PDF reports, provenance and `reconstruct.sh`.

Saving a package does not start a reconstruction or simulation. The exported launcher runs placement and connectivity using **`mpirun -n 8`** and protects existing output folders. Allocate eight CPU/MPI slots to the VM before reconstructing; memory and disk needs depend on network size. The GUI itself can be used with fewer CPUs.

After activating the environment, run these commands from an exported package directory:

```bash
bash reconstruct.sh --check
bash reconstruct.sh
```

Do not prefix the script with another `mpirun`. The completed network is saved as `reconstruction/network.hdf5`. Electrical parameter files do not define a stimulation protocol.

## Included versions and scope

| Component | Version |
|---|---|
| Ubuntu target | 24.04 LTS, Python 3.12 |
| BSB and native library | 8.0.2 |
| cerebellar-models | 0.13.0 |
| Cerebellum Designer | 0.0.1 |

The included official model checkout is pinned to commit `e77be2d0e9ea907a7672c7ab10a9279050fcd024`. Dependency constraints are included. This is a tested combination, not an automatic selection of the newest upstream versions.

The current Designer supports the mouse cortical model and uniform population effects. It does not add DCN/IO, learn new dendritic branches, or validate a disease hypothesis physiologically. The SZ preset is exploratory and includes parameter-level evidence notes. The portable export rejects heterogeneous or individual-cell recipes rather than silently flattening them.

**NEST and NEURON are not included.** They are not needed for Designer and structural reconstruction. Electrical simulations require a separately configured simulator; EGLIF simulations also require the model's compiled NESTML extension.

## Verification

The installation was exercised in a new Python 3.12 environment on Ubuntu 24.04. Checks covered dependencies, eight MPI processes, server startup, model and morphology catalogs, YAML/SWC/PDF export and the exported launcher's environment check. The export implementation was also verified with two small complete MPI-8 reconstruction fixtures. These checks are software validation, not biological validation or a benchmark for every Windows host/VM configuration.

The Windows wrapper adds PowerShell syntax/argument/integrity checks, extraction tests with spaces and apostrophes, and safeguards against overwriting unrelated folders, changed source or results. GitHub Actions runs the launcher contracts under Windows PowerShell 5.1 and PowerShell 7. Those checks do not provision WSL or replace a complete Windows installation test.

## Sources and notices

- [BSB installation and MPI documentation](https://bsb.readthedocs.io/en/latest/getting-started/installation.html)
- [Official cerebellar-models repository](https://github.com/dbbs-lab/cerebellar-models)
- The original model license and attribution are retained inside the kit under `src/cerebellar-models/`. The third-party JavaScript library retains its license header. Third-party components retain their own license terms.

The archive is a source-code installation kit, not a prebuilt virtual machine. Future packaged updates should be extracted into a new directory; do not overwrite an existing environment or scientific output.
