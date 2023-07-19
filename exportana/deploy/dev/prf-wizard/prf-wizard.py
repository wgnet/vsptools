import os
import shutil
import requests
import posixpath
import subprocess

from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from urllib.parse import urljoin
from g3_metaconfig import G3ConfigMeta, Param

TRUE_CHOICE = ['true', '1', 'yes', '+', 'y']
FALSE_CHOICE = ['false', '0', 'no', '-', 'n']

WORK_DIR = Path(os.getcwd())


def as_bool(value: str):
    if str_or_none(value) is not None:
        if value.lower() in TRUE_CHOICE:
            return True
        elif value.lower() in FALSE_CHOICE:
            return False
        else:
            raise ValueError
    else:
        return False


def str_or_none(string: str):
    return string or None


# without this we have wrong slashes in docker-compose volume path
def wsl_path_changer(win_path: Path):
    linux_pattern_path = Path('/mnt/')

    for part in win_path.parts:
        if part == win_path.parts[0] and part.find(':') != -1:
            linux_pattern_path = Path(linux_pattern_path, part.replace(':', '').lower())
        else:
            linux_pattern_path = Path(linux_pattern_path, part)

    return linux_pattern_path.as_posix()


def return_to_work_dir():
    os.chdir(WORK_DIR)


class Config(metaclass=G3ConfigMeta):
    class Config:
        auto_replace_underscores_with_dashes = False

    class ArgParserConfig:
        default_config_files = ['./configs/prf-wizard_defaults.yml', './configs/prf-wizard.yml']

    config: str = Param(is_config_file=True, help="Full path to prf-master.yml")
    installation_folder: str = Param(required=True, type=str_or_none, help="Folder for installation")

    # Installation components
    setup: bool = Param(required=True, type=as_bool, help="Setup installation flag")
    update: bool = Param(required=True, type=as_bool, help="Update artifacts flag")
    tracer: bool = Param(required=True, type=as_bool, help="Tracer installation flag")
    exportana_worker: bool = Param(required=True, type=as_bool, help="Exportana_worker installation flag")
    exportana_manager: bool = Param(required=True, type=as_bool, help="Exportana_manager installation flag")

    # Unreal components
    ue_version: str = Param(required=True, type=str_or_none, help="UE version of components")

    #    Tracer
    tracer_artifact_name: str = Param(required=True, type=str_or_none, help="Name of tracer component in artifactory")
    tracer_artifactory_repository: str = Param(required=True, type=str_or_none, help="Repository of tracer")

    #    Unreal Insights
    unrealinsights_artifact_name: str = Param(required=True, type=str_or_none, help="UI artifact name")
    unrealinsights_artifactory_repository: str = Param(required=True, type=str_or_none, help="Repository of UI")

    # Exportana
    exportana_version: str = Param(required=True, type=str_or_none, help="Version of exportana")

    #    Worker
    worker_name: str = Param(required=True, type=str_or_none, help="Name of worker")
    worker_port: str = Param(required=True, type=str_or_none, help="Worker port")
    worker_extra_args: str = Param(required=True, type=str_or_none, help="Worker extra args")
    worker_config_name: str = Param(required=True, type=str_or_none, help="Config file for worker")
    worker_artifact_name: str = Param(required=True, type=str_or_none, help="Name of exportana artifact")
    worker_artifactory_repository: str = Param(required=True, type=str_or_none,
                                               help="Repository of exportana in artifactory")
    #    Manager
    manager_url: str = Param(required=True, type=str_or_none, help="Manager url (for worker connect)")
    manager_port: str = Param(required=True, type=str_or_none, help="Manager port")
    manager_extra_args: str = Param(required=True, type=str_or_none, help="Worker extra args")
    manager_config_name: str = Param(required=True, type=str_or_none, help="Config file for manager")
    manager_mongo_version: str = Param(required=True, type=str_or_none, help="MongoDB version (for manager)")
    manager_artifactory_repository: str = Param(required=True, type=str_or_none, help="Repository of manager")
    manager_env_artifactory_repository: str = Param(required=True, type=str_or_none, help="Repository of manager env")
    manager_container_source_trace_sessions: str = Param(required=True, type=str_or_none, help="Container trace store")
    # Other
    artifactory_url: str = Param(required=True, type=str_or_none, help="Artifactory url (without protocol,port)")
    elk_stack_version: str = Param(required=True, type=str_or_none, help="Version of ELK-stack")

    elastic_url: str = Param(required=True, type=str_or_none, help="Elastic url (http://user:PassOrToken@url:port)")
    bitbucket_url: str = Param(required=True, type=str_or_none, help="BitBucket url (http://user:PassOrToken@url:port)")

    perfana_url: str = Param(required=True, type=str_or_none, help="Perfana url")
    perfana_version: str = Param(required=True, type=str_or_none, help="Perfana version")

    debug_mode: bool = Param(required=True, type=as_bool, help="Debug mode flag")


# - - - - - Constants - - - - -
class Constants:
    class Services:
        instances = []

        def __init__(self, name, version, artifact_name, artifactory_repository):
            self.name = name
            self.version = version
            self.artifact_name = artifact_name
            self.artifactory_repository = artifactory_repository
            self.instances.append(self)

    if Config.worker_name is None:
        Config.worker_name = os.environ['COMPUTERNAME']

    if str(Config.installation_folder)[0] == '.':
        INSTALLATION_FOLDER: Path = Path(WORK_DIR, Config.installation_folder)
    else:
        INSTALLATION_FOLDER: Path = Config.installation_folder

    DOWNLOAD_FOLDER: Path = Path(INSTALLATION_FOLDER, 'downloads')

    TRACER_BIN_EXE: Path = Path('Tracer/Engine/Binaries/Win64/Tracer.exe')
    UNREALINSIGHTS_BIN: Path = Path('UnrealInsights/Engine/Binaries/Win64')
    UNREALINSIGHTS_TRACE_SESSIONS: Path = Path('UnrealInsights/Engine/Programs/UnrealInsights/Saved/TraceSessions')

    UNDELETED_EXTENSIONS: list = ['.conf', '.log', '.csv', '.utrace', '.live']

    INSTALLATION_VERSIONED_FOLDER: Path = Path(INSTALLATION_FOLDER, Config.exportana_version)
    UNREALINSIGHTS_SOURCE: Path = Path(INSTALLATION_VERSIONED_FOLDER, UNREALINSIGHTS_TRACE_SESSIONS)
    UNREALINSIGHTS_SOURCE_MNT: Path = wsl_path_changer(UNREALINSIGHTS_SOURCE)

    Worker = Services(name='Worker',
                      version=Config.exportana_version,
                      artifact_name=Config.worker_artifact_name,
                      artifactory_repository=Config.worker_artifactory_repository)

    Tracer = Services(name='Tracer',
                      version=Config.ue_version,
                      artifact_name=Config.tracer_artifact_name,
                      artifactory_repository=Config.tracer_artifactory_repository)

    UnrealInsights = Services(name='UnrealInsights', version=Config.ue_version,
                              artifact_name=Config.unrealinsights_artifact_name,
                              artifactory_repository=Config.unrealinsights_artifactory_repository)

    EXPORTANA_CONFIG_PARAMS: dict = {
        'work-mode': 'worker',
        'config': Config.worker_config_name,
        'perfana': Config.perfana_url,
        'elastic': Config.elastic_url,
        'bitbucket': Config.bitbucket_url,
        'source': str(UNREALINSIGHTS_SOURCE).replace(r'\TraceSessions', ''),
        'insights': f'{Path(INSTALLATION_VERSIONED_FOLDER, UNREALINSIGHTS_BIN)}',
        'worker-name': Config.worker_name,
        'manager-url': Config.manager_url,
        'port': Config.worker_port,
    }

    DOCKER_COMPOSE_PARAMS: dict = {
        'manager':
            {
                'perfana_url': Config.perfana_url,
                'elastic_url': Config.elastic_url,
                'manager_port': Config.manager_port,
                'bitbucket_url': Config.bitbucket_url,
                'exportana_version': Config.exportana_version,
                'manager_extra_args': Config.manager_extra_args,
                'artifactory_manager': f'{Config.artifactory_url}:8081/{Config.manager_artifactory_repository}',
                'manager_config_name': Config.manager_config_name,
                'manager_mongo_version': Config.manager_mongo_version,
                'unrealinsights_source': UNREALINSIGHTS_SOURCE_MNT,
                'manager_container_source_trace_sessions': Config.manager_container_source_trace_sessions,
            },
        'manager-environment':
            {
                'perfana_version': Config.perfana_version,
                'elk_stack_version': Config.elk_stack_version,
                'manager_mongo_version': Config.manager_mongo_version,
                'artifactory_manager_environment': f'{Config.artifactory_url}:8081/'
                                                   f'{Config.manager_env_artifactory_repository}',
            }
    }


def setup():
    def poetry_check():
        if os.system('poetry -V') == 1:
            print('poetry not found\nplease, install it from https://python-poetry.org/docs/')
            return 1
        else:
            return 0

    def setx_envs():
        envs = {
            'TRACER_STORE': Constants.UNREALINSIGHTS_SOURCE,
        }

        for env in envs.keys():
            if envs.get(env) is not None:
                print(f'\nenv {env} = {envs.get(env)}')
                os.system(f'setx {env} {envs.get(env)}')
                os.putenv(env, str(envs.get(env)))
            else:
                raise ValueError(f'Environment variable "{env}" value is None.')

    poetry_check()
    setx_envs()


def update():
    def cleanup_folders(folders: list):
        for folder in folders:
            if os.path.exists(folder):
                for filename in os.listdir(folder):
                    file_path = Path(folder, filename)
                    file_extension = os.path.splitext(filename)[1]
                    try:
                        if os.path.isfile(file_path) and file_extension not in Constants.UNDELETED_EXTENSIONS:
                            os.remove(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as e:
                        print(f'Failed to delete {file_path}. Reason: {e}')
        return True

    def cleanup():
        cleanup_folders([Constants.DOWNLOAD_FOLDER, Constants.INSTALLATION_VERSIONED_FOLDER])

        for folder in [Constants.DOWNLOAD_FOLDER, Constants.UNREALINSIGHTS_SOURCE]:
            os.makedirs(folder, exist_ok=True)
            print(f'\nFolder created {folder}')

    def request_to_artifactory(path_to_artifact, artifactory_url):
        r = requests.get(artifactory_url, stream=True)

        if r.ok:
            print(f'Successfully downloaded from {artifactory_url=}')
        else:
            r.raise_for_status()

        with open(path_to_artifact, 'wb') as fd:
            for chunk in r.iter_content(chunk_size=128):
                fd.write(chunk)

    def download_artifacts(artifactory_url=Config.artifactory_url):
        for instance in Constants.Services.instances:
            service_artifactory_url = urljoin('http://' + artifactory_url, 'artifactory/' +
                                              posixpath.join(instance.__dict__['artifactory_repository'],
                                                             instance.__dict__['version'],
                                                             instance.__dict__['artifact_name']))

            print(f'download from {service_artifactory_url}')

            path_to_artifact = Path(Constants.DOWNLOAD_FOLDER, instance.__dict__['artifact_name'])
            request_to_artifactory(path_to_artifact=path_to_artifact, artifactory_url=service_artifactory_url)
            os.system(f'7z x "{path_to_artifact}" '
                      f'-o"{Path(Constants.INSTALLATION_VERSIONED_FOLDER, instance.__dict__["name"])}" -y')

    def poetry_build_worker_package():
        os.chdir(Path(Constants.INSTALLATION_VERSIONED_FOLDER, 'Worker'))

        os.system('poetry build - f wheel')
        os.system('poetry install')

        return_to_work_dir()

    cleanup()
    download_artifacts()
    poetry_build_worker_package()


def start_worker():
    exportana_run_command = f'start poetry run exportana'

    for param in Constants.EXPORTANA_CONFIG_PARAMS.keys():

        if Constants.EXPORTANA_CONFIG_PARAMS.get(param) is not None:
            exportana_run_command += ' --' + ' '.join([param, str(Constants.EXPORTANA_CONFIG_PARAMS.get(param))])

    if Config.worker_extra_args is not None:
        exportana_run_command += ' ' + ' '.join([Config.worker_extra_args])

    os.chdir(Path(Constants.INSTALLATION_VERSIONED_FOLDER, 'Worker'))

    cmd = f'{exportana_run_command}'
    exportana_process = subprocess.check_call(args=cmd, shell=True)

    return_to_work_dir()

    return exportana_process


def start_tracer():
    os.system(f'start {Path.joinpath(Path(Constants.INSTALLATION_VERSIONED_FOLDER),Constants.TRACER_BIN_EXE)}')


def docker_compose_update_envs(service_name):
    file_loader = FileSystemLoader('./templates')
    env = Environment(loader=file_loader)

    template = env.get_template(f'{service_name}-compose.j2')

    output = template.render(Constants.DOCKER_COMPOSE_PARAMS.get(service_name))
    return output


def docker_compose_update_file(service_name):
    new_content = docker_compose_update_envs(service_name)

    os.makedirs(service_name, exist_ok=True)

    with open(Path(service_name, 'docker-compose.yml'), 'w') as f:
        f.write(new_content)
        f.close()


def docker_compose_service_down(service_name):
    os.chdir(service_name)
    os.system('docker-compose down --remove-orphans')
    return_to_work_dir()


def docker_compose_service_up(service_name):
    docker_compose_update_file(service_name=service_name)

    os.chdir(service_name)
    os.system('docker-compose up -d')
    return_to_work_dir()


def main():
    if Config.debug_mode:
        for wizard_class in [Config, Constants]:
            print(f'\n- - - - - {wizard_class.__name__} - - - - -\n')
            for field_name in wizard_class.__annotations__.keys():
                if type(getattr(wizard_class, field_name)) != dict:
                    print(f'{field_name} = {getattr(wizard_class, field_name)}')
                else:
                    print(f'\n{field_name}:')
                    for attr in getattr(wizard_class, field_name):
                        if type(getattr(wizard_class, field_name)[attr]) != dict:
                            print(f'  {attr} = {getattr(wizard_class, field_name)[attr]}')
                        else:
                            print(f'  {attr}:')
                            for sub_attr in getattr(wizard_class, field_name)[attr]:
                                print(f'    {sub_attr} = {getattr(wizard_class, field_name)[attr][sub_attr]}')
            for instance in Constants.Services.instances:
                for key in instance.__dict__:
                    if key == 'name':
                        print(f'\n{instance.__dict__[key]}')
                    else:
                        print(f'  {key} = {instance.__dict__[key]}')
            print(f'\n- - - - - {wizard_class.__name__} - - - - -\n')

    if Config.setup:
        setup()

    if Config.update:
        update()

    if Config.exportana_worker:
        start_worker()

    if Config.tracer:
        start_tracer()

    if Config.exportana_manager:
        for manager_service in ['manager', 'manager-environment']:
            docker_compose_service_down(service_name=manager_service)
            docker_compose_service_up(service_name=manager_service)


if __name__ == "__main__":
    exit(main())
