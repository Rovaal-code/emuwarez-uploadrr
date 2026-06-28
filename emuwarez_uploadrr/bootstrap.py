"""Bootstrap, venv and dependency management."""
from .legacy import (
    parse_python_version, python_version, python_executable_path,
    ensure_launcher_python_supported, confirm_launcher_python_recommended,
    choose_venv_python, venv_version, check_venv_python_version,
    maybe_offer_system_update, command_exists, install_system_packages,
    ensure_system_tools, maybe_offer_python311_install, venv_has_pip,
    repair_pip_with_ensurepip, recreate_venv, ensure_venv_ready, run_pip,
    create_venv_if_needed, local_modules, stdlib_modules, scan_python_imports,
    external_imports_uploadrr, module_available_in_venv, scan_imports_command,
    requirement_name, requirement_lines, install_requirement_line,
    install_uploadrr_declared_deps, pip_package_for_import,
    missing_module_from_output, install_missing_uploadrr_imports, uploadrr_help_probe,
    install_one_missing_module, ensure_uploadrr_startup_ready, check_uploadrr,
    bootstrap, ensure_runtime_ready,
)
