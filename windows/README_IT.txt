CEREBELLUM DESIGNER 0.0.1 - WINDOWS + WSL2
Maintainer: Alberto Arturo Vergani
Windows launcher: 2026-11-24

La dashboard si apre nel browser Windows. Il motore BSB gira in WSL2 con
Ubuntu 24.04, senza dover aprire una VM con desktop. Non e' un eseguibile
Windows nativo indipendente da Linux. La VM Ubuntu gia' installata resta
utilizzabile con il pacchetto Ubuntu: WSL2 e' un'alternativa, non un requisito
aggiuntivo per la tua VM.

REQUISITI
- Windows 11 x64 o Windows 10 x64 con supporto WSL2 (build 19041 o successiva).
- Virtualizzazione hardware abilitata e WSL2; Ubuntu 24.04 con utente normale.
- Internet per installare dipendenze apt/pip.
- 8 CPU visibili in WSL per ricostruire con mpirun -n 8. Il Designer puo'
  aprirsi con meno CPU. RAM e spazio richiesti dipendono dalla rete.
- Windows ARM non verificato in questo pacchetto.

PRIMO AVVIO
1. Scarica CerebellumDesigner_Windows_WSL2_20261124.zip da GitHub.
2. Estrai TUTTO lo ZIP in una cartella locale Windows, per esempio Documenti.
   Non avviare i comandi dall'interno dello ZIP. Tieni insieme tutti i file.
3. Se non hai WSL2/Ubuntu 24.04, apri PowerShell come amministratore e lancia:

   wsl --install -d Ubuntu-24.04

   Riavvia se richiesto. Apri Ubuntu dal menu Start e scegli username e password.
   I caratteri della password Linux non vengono visualizzati: e' normale.
   Controlla: wsl --list --verbose . Ubuntu-24.04 deve indicare VERSION 2.
   Se indica 1: wsl --set-version Ubuntu-24.04 2

4. Doppio clic su 1_Install_Designer.cmd come utente normale Windows.
   L'installer richiede la password Linux per apt e prepara un ambiente isolato.
   Verifica anche l'integrita' del pacchetto; non cambia modelli o simulazioni
   presenti in altre cartelle. Aspetta il messaggio di installazione completata.
5. Doppio clic su 2_Start_Designer.cmd.
   Si apre http://127.0.0.1:8891/ nel browser Windows.
   Lascia aperta la finestra del server; Ctrl+C in quella finestra lo arresta.

USO SUCCESSIVO
- 2_Start_Designer.cmd: apre la dashboard; se e' gia' aperta riutilizza il server.
- 3_Open_Exports.cmd: apre gli export in Esplora file Windows.
- 4_Reconstruction_Terminal.cmd: apre Bash con l'ambiente BSB gia' attivo.
  Non avvia ricostruzioni automaticamente.

FILE E RICOSTRUZIONE
L'app e i dati sono nel filesystem Linux di WSL:
  ~/CerebellumDesigner_WSL
Gli export sono in:
  ~/CerebellumDesigner_WSL/DeformationAlgorithm/exports
Aprili da Windows con 3_Open_Exports.cmd. Salva una copia degli export importanti
anche sul disco esterno. Disinstallare/eliminare la distribuzione WSL elimina
anche i dati che contiene: non usare wsl --unregister per aggiornare il Designer.

Nel Designer configura Cells/Network e usa Review & save. Ogni pacchetto include
structural.yaml, le SWC trasformate, parametri elettrici, report HTML/PDF e script.
Per ricostruire, apri 4_Reconstruction_Terminal.cmd e lancia:

  cd DeformationAlgorithm/exports/<nome_pacchetto>
  bash reconstruct.sh --check
  bash reconstruct.sh

Lo script usa mpirun -n 8 per placement e connettivita'. Non aggiungere un altro
mpirun davanti. Rifiuta di sovrascrivere l'output gia' esistente. Il risultato
e' reconstruction/network.hdf5. Il salvataggio dalla GUI non avvia alcun run.
Non sono inclusi NEST/NEURON e non vengono lanciate simulazioni elettriche.

RISOLUZIONE PROBLEMI
- Porta occupata: apri un terminale nella cartella Windows e usa
    .\2_Start_Designer.cmd -Port 8893
  Non serve chiudere l'altra applicazione.
- Ubuntu gia' installato con un altro nome (ma versione 24.04):
    .\1_Install_Designer.cmd -Distribution Ubuntu
    .\2_Start_Designer.cmd -Distribution Ubuntu
  Usa lo stesso -Distribution anche per gli altri comandi.
- La pagina non si apre: controlla la finestra del server e la configurazione
  WSL localhostForwarding. Non e' necessario aprire una porta sulla rete esterna.
- Script bloccati da policy aziendale: segui la policy del tuo PC; usa in
  alternativa i comandi Bash del kit Ubuntu. I launcher impostano una policy
  solo per il proprio processo PowerShell, senza cambiare quella di sistema.
- Un'installazione incompleta puo' essere ripresa dallo stesso installer.
  Cartelle estranee o sorgenti modificate non vengono sovrascritte.
- I file .cmd restano nella cartella Windows estratta. L'ambiente Python e i
  dati restano nella Home Linux, anche se sposti questa cartella Windows.

VERSIONI E VERIFICHE
BSB 8.0.2, cerebellar-models 0.13.0 (commit e77be2d0...), Python 3.12,
Cerebellum Designer 0.0.1. La sorgente scientifica del kit Ubuntu e' invariata.
Archivio incluso SHA256:
d98bff221871c5e18678ebaf5dfdacc866c06ee444f076a7476968d791704b17

Il backend Ubuntu e l'export sono stati verificati con dipendenze, MPI8 e due
piccole ricostruzioni. I nuovi launcher hanno controlli di sintassi e test di
percorsi/errori/integrita'. Un'installazione completa sul tuo Windows/WSL2 deve
ancora essere verificata: questi test non sostituiscono una prova end-to-end
su una macchina Windows. Non dichiarare validazione biologica da questi test.

Documentazione ufficiale:
https://learn.microsoft.com/windows/wsl/install
https://learn.microsoft.com/windows/wsl/networking
https://bsb.readthedocs.io/en/latest/getting-started/installation.html
Repository: https://github.com/albertoarturovergani/CerebellumDesigner
