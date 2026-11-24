[[ ! -f "$HOME/.bashrc" ]] || source "$HOME/.bashrc"
source "$CD_WINDOWS_INSTALL_ROOT/activate.sh"
cd "$CD_WINDOWS_INSTALL_ROOT"
printf '%s\n' 'Designer environment active. Export a package, then:' \
    'cd DeformationAlgorithm/exports/<package>' \
    'bash reconstruct.sh --check' \
    'bash reconstruct.sh' \
    'The exported script uses mpirun -n 8. No simulation is started.'
