CEREBELLUM DESIGNER 0.0.1 — WINDOWS NATIVO x64
Maintainer: Alberto Arturo Vergani

Non richiede Ubuntu, WSL, una macchina virtuale, Python o BSB installati.

AVVIO
1. Scarica CerebellumDesigner_Windows_x64.zip dalla pagina Releases ufficiale:
   https://github.com/albertoarturovergani/CerebellumDesigner/releases
2. Estrai l'intero ZIP in una cartella locale. Non aprire l'EXE dentro lo ZIP.
3. Apri CerebellumDesigner.exe. La dashboard si apre nel browser Windows.
   Mantieni la cartella _internal accanto all'EXE: contiene il runtime incluso.
4. Per chiudere il programma usa Close app in alto. Chiudere solo la scheda
   del browser non arresta il server locale.

PRESET SZ
Nel menu Preload a profile scegli SZ - structure + NMDA e premi Load profile.
Le modifiche, gli slider e le referenze sono inclusi nel programma.
Il profilo iniziale è Healthy: il preset SZ non si applica senza selezionarlo.
Il preset è esplorativo e distingue le evidenze dalle scelte modellistiche.

FILE SALVATI
Il programma salva profili ed esportazioni nella cartella:
  %LOCALAPPDATA%\CerebellumDesigner\DeformationAlgorithm
Le impostazioni restano al riavvio tramite Save to profile list e il menu Preload.
In Review & save, Save & download ZIP produce YAML strutturali ed elettrici,
morfologie SWC già trasformate, report HTML/PDF, riferimenti, manifest con hash
e uno script reconstruct.sh con MPI a 8 processi.
La posizione effettiva è mostrata anche in Bundled model & file locations.

COSA FA QUESTA VERSIONE
Editor nativo, morfologie 3D, dendrogramma/DCI, tilt, rotazioni, parametri
strutturali ed elettrici, anteprima di rete proporzionale ed esportazione.
Le coordinate sane di riferimento derivano da un vero placement BSB.
I conteggi modificati mostrati in anteprima sono stime, non nuove ricostruzioni.

RICOSTRUZIONE E SIMULAZIONI
Il Designer nativo non esegue BSB/MPI, NEST o NEURON in Windows.
Il pacchetto esportato va trasferito a un ambiente BSB 8 / MPI compatibile,
per esempio la workstation o un HPC. Non serve Ubuntu sul PC usato per
progettare ed esportare. Sul computer BSB, attiva l'ambiente corrispondente,
entra nella cartella estratta del pacchetto ed esegui:
  bash reconstruct.sh --check
  bash reconstruct.sh
Non riapplicare il profilo alle SWC: le trasformazioni sono già incorporate.
I file elettrici sono parametri di modello: non definiscono uno stimolo.

VERSIONI
Designer 0.0.1. Sorgente cerebellar-models 0.13.0 inclusa, commit
  e77be2d0e9ea907a7672c7ab10a9279050fcd024
Target della ricostruzione BSB 8.0.2. Queste versioni non sono installazioni
richieste sul PC Windows dell'editor.

DIAGNOSTICA
Log: %LOCALAPPDATA%\CerebellumDesigner\desktop.log
Errori di avvio: %LOCALAPPDATA%\CerebellumDesigner\last-error.txt
Il server ascolta soltanto su 127.0.0.1. Non richiede permessi amministratore.
Il pacchetto è x64; Windows ARM non è stato verificato.
L'eseguibile non è firmato con certificato Authenticode.
I test automatici sono eseguiti su un runner Windows; non coprono ogni driver
WebGL o configurazione di sicurezza del PC personale.
