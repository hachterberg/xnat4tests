import tempfile
from pathlib import Path
import traceback
import yaml
import pytest
import docker
from xnat4tests.utils import set_loggers
from xnat4tests.config import Config
from xnat4tests import start_xnat, stop_xnat, connect
from xnat4tests.cli import cli as x4t_cli


def show_cli_trace(result):
    return "".join(traceback.format_exception(*result.exc_info))


@pytest.fixture(scope="session")
def home_dir():  # Makes the home dir show up on test output
    return Path(tempfile.mkdtemp())


@pytest.fixture(scope="session")
def config(home_dir):

    config_path = home_dir / "configs" / "test-config.yaml"
    config_path.parent.mkdir()
    plugin_path = home_dir / "plugins" / "default"
    plugin_path.mkdir(parents=True)
    with open(plugin_path / "test.txt", "w") as f:
        f.write("test")
    with open(config_path, "w") as f:
        yaml.dump(
            {
                "docker_image": "xnat4tests_unittest",
                "docker_container": "xnat4tests_unittest",
                "xnat_mnt_dirs": ["plugins"],
                "xnat_port": "8090",
                "registry_port": "5555",
                "xnat_root_dir": str(home_dir / "xnat_root"),
                "build_args": {"java_mx": "1g"},
            },
            f,
        )

    set_loggers("debug")

    return Config.load(config_path)


@pytest.fixture(scope="session")
def login(config):

    dc = docker.from_env()
    try:
        container = dc.containers.get(config.docker_container)
    except docker.errors.NotFound:
        pass
    else:
        container.stop()

    try:
        image = dc.images.get(config.docker_image)
    except docker.errors.ImageNotFound:
        pass
    else:
        dc.images.remove(image.id)

    start_xnat(config)
    yield connect(config)
    stop_xnat(config)


def test_config(config, home_dir):

    assert config.xnat_root_dir == home_dir / "xnat_root"
    assert config.xnat_mnt_dirs == ["plugins"]
    assert config.docker_image == "xnat4tests_test"
    assert config.docker_container == "xnat4tests_test"
    assert config.xnat_port == "8090"
    assert config.registry_port == "5555"
    assert config.build_args.xnat_ver == "1.8.5"
    assert config.build_args.xnat_cs_plugin_ver == "3.2.0"
    assert config.build_args.xnat_batch_launch_plugin_ver == "0.6.0"
    assert config.build_args.java_ms == "256m"
    assert config.build_args.java_mx == "1g"


def test_launch(config, login):

    PROJECT = "MY_TEST_PROJECT"
    SUBJECT = "MY_TEST_SUBJECT"
    SESSION = "MY_TEST_SESSION"

    # Create project
    login.put(f"/data/archive/projects/{PROJECT}")

    # Create subject
    xsubject = login.classes.SubjectData(label=SUBJECT, parent=login.projects[PROJECT])
    # Create session
    xsession = login.classes.MrSessionData(label=SESSION, parent=xsubject)

    temp_dir = Path(tempfile.mkdtemp())
    a_file = temp_dir / "a_file.txt"
    with open(a_file, "w") as f:
        f.write("a file")

    xresource = login.classes.ResourceCatalog(
        parent=xsession, label="A_RESOURCE", format="text"
    )
    xresource.upload(str(a_file), "a_file")

    assert [p.name for p in (config.xnat_root_dir / "archive").iterdir()] == [
        PROJECT
    ]
    assert [
        p.name
        for p in (config.xnat_root_dir / "archive" / PROJECT / "arc001").iterdir()
    ] == [SESSION]

    assert list((config.xnat_root_dir / "plugins").iterdir()) == ["test.txt"]


def test_cli(cli_runner):

    result = cli_runner(
        x4t_cli,
        ["--config", "default", "--help"]
    )

    assert result.exit_code == 0, show_cli_trace(result)
