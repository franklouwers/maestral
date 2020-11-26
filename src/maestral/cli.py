# -*- coding: utf-8 -*-
"""
This file defines the functions to configure and interact with Maestral from the command
line. Some imports are deferred to the functions that required them in order to reduce
the startup time of individual CLI commands.
"""

# system imports
import sys
import os
import os.path as osp
import functools
import time
from typing import Optional, Dict, Iterable, Callable, Union, cast, TYPE_CHECKING

# external imports
import click
import Pyro5.errors  # type: ignore

# local imports
from . import __version__, __author__, __url__
from .utils import cli

if TYPE_CHECKING:
    from .main import Maestral
    from .daemon import MaestralProxy


# ======================================================================================
# CLI dialogs and helper functions
# ======================================================================================

OK = click.style("[OK]", fg="green")
FAILED = click.style("[FAILED]", fg="red")
KILLED = click.style("[KILLED]", fg="red")


def stop_daemon_with_cli_feedback(config_name: str) -> None:
    """Wrapper around :meth:`daemon.stop_maestral_daemon_process`
    with command line feedback."""

    from .daemon import stop_maestral_daemon_process, Stop

    click.echo("Stopping Maestral...", nl=False)
    res = stop_maestral_daemon_process(config_name)
    if res == Stop.Ok:
        click.echo(" " * 8 + OK)
    elif res == Stop.NotRunning:
        click.echo("\rMaestral daemon is not running.")
    elif res == Stop.Killed:
        click.echo(" " * 8 + KILLED)
    elif res == Stop.Failed:
        click.echo(" " * 8 + FAILED)


def select_dbx_path_dialog(
    config_name: str, default_dir_name: Optional[str] = None, allow_merge: bool = False
) -> str:
    """
    A CLI dialog to ask for a local Dropbox folder location.

    :param config_name: The configuration to use for the default folder name.
    :param default_dir_name: The default directory name. Defaults to
        "Dropbox ({config_name})" if not given.
    :param allow_merge: If ``True``, allows the selection of an existing folder without
        deleting it. Defaults to ``False``.
    :returns: Path given by user.
    """

    from .utils.path import delete

    default_dir_name = default_dir_name or f"Dropbox ({config_name.capitalize()})"

    while True:
        res = cli.select_path(
            "Please choose a local Dropbox folder:",
            default=f"~/{default_dir_name}",
            only_directories=True,
        )
        res = res.rstrip(osp.sep)

        dropbox_path = osp.expanduser(res)

        if osp.exists(dropbox_path):
            if allow_merge:
                text = (
                    "Directory already exists. Do you want to replace it "
                    "or merge its content with your Dropbox?"
                )
                choice = cli.select(text, options=["replace", "merge", "cancel"])
            else:
                text = (
                    "Directory already exists. Do you want to replace it? "
                    "Its content will be lost!"
                )
                replace = cli.confirm(text)
                choice = 0 if replace else 2

            if choice == 0:
                err = delete(dropbox_path)
                if err:
                    cli.warn(
                        "Could not write to selected location. "
                        "Please make sure that you have sufficient permissions."
                    )
                else:
                    cli.ok("Replaced existing folder")
                    return dropbox_path
            elif choice == 1:
                cli.ok("Merging with existing folder")
                return dropbox_path

        else:
            return dropbox_path


def link_dialog(m: Union["MaestralProxy", "Maestral"]) -> None:
    """
    A CLI dialog for linking a Dropbox account.

    :param m: Proxy to Maestral daemon.
    """

    authorize_url = m.get_auth_url()

    config_name = click.style(m.config_name, bold=True)
    cli.info(f"Linking new account for {config_name} config")
    cli.info("Retrieving auth code from Dropbox")
    choice = cli.select(
        "How would you like to you link your account?",
        options=["Open Dropbox website", "Print auth URL to console"],
    )

    if choice == 0:
        click.launch(authorize_url)
    else:
        cli.info("Open the URL below to retrieve an auth code:")
        cli.info(authorize_url)

    res = -1
    while res != 0:
        auth_code = cli.prompt("Enter the auth code:")
        auth_code = auth_code.strip()

        res = m.link(auth_code)

        if res == 0:
            email = click.style(m.get_state("account", "email"), bold=True)
            cli.ok(f"Linked to {email}")
        elif res == 1:
            cli.warn("Invalid token, please try again")
        elif res == 2:
            cli.warn(" Could not connect to Dropbox, please try again")


def check_for_updates() -> None:
    """
    Checks if updates are available by reading the cached release number from the
    config file and notifies the user. Prints an update note to the command line.
    """
    from packaging.version import Version
    from .config import MaestralConfig, MaestralState

    conf = MaestralConfig("maestral")
    state = MaestralState("maestral")

    interval = conf.get("app", "update_notification_interval")
    last_update_check = state.get("app", "update_notification_last")
    latest_release = state.get("app", "latest_release")

    if interval == 0 or time.time() - last_update_check < interval:
        return

    has_update = Version(__version__) < Version(latest_release)

    if has_update:
        cli.echo(
            f"Update available v{__version__} → v{latest_release}. "
            f"Please use your package manager to update."
        )


def check_for_fatal_errors(m: Union["MaestralProxy", "Maestral"]) -> bool:
    """
    Checks the given Maestral instance for fatal errors such as revoked Dropbox access,
    deleted Dropbox folder etc. Prints a nice representation to the command line.

    :param m: Proxy to Maestral daemon or Maestral instance.
    :returns: True in case of fatal errors, False otherwise.
    """

    import textwrap

    maestral_err_list = m.fatal_errors

    if len(maestral_err_list) > 0:

        width, height = click.get_terminal_size()

        err = maestral_err_list[0]
        err_title = cast(str, err["title"])
        err_msg = cast(str, err["message"])

        wrapped_msg = textwrap.fill(err_msg, width=width)

        click.echo("")
        click.secho(err_title, fg="red")
        click.secho(wrapped_msg, fg="red")
        click.echo("")

        return True
    else:
        return False


def catch_maestral_errors(func: Callable) -> Callable:
    """
    Decorator that catches a MaestralApiError and prints it as a useful message to the
    command line instead of printing the full stacktrace.
    """

    from .errors import MaestralApiError

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except MaestralApiError as exc:
            raise cli.RemoteApiError(exc.title, exc.message)
        except ConnectionError:
            raise cli.CliException("Could not connect to Dropbox")

    return wrapper


# ======================================================================================
# Custom parameter types
# ======================================================================================

# A custom parameter:
# * needs a name
# * needs to pass through None unchanged
# * needs to convert from a string
# * needs to convert its result type through unchanged (eg: needs to be idempotent)
# * needs to be able to deal with param and context being None. This can be the case
#   when the object is used with prompt inputs.


class DropboxPath(click.ParamType):
    """A command line parameter representing a Dropbox path

    :param file_okay: Controls if a file is a possible value.
    :param dir_okay: Controls if a directory is a possible value.
    """

    name = "Dropbox path"
    envvar_list_splitter = osp.pathsep

    def __init__(self, file_okay: bool = True, dir_okay: bool = True) -> None:
        self.file_okay = file_okay
        self.dir_okay = dir_okay

    #
    # def shell_complete(
    #     self,
    #     ctx: Optional[click.Context],
    #     param: Optional[click.Parameter],
    #     incomplete: str,
    # ) -> List["CompletionItem"]:
    #
    #     from click.shell_completion import CompletionItem
    #     from .utils import removeprefix
    #
    #     matches: List[str] = []
    #
    #     # check if we have been given an absolute path
    #     incomplete = incomplete.lstrip("/")
    #
    #     # get the Maestral config for which to complete paths
    #     try:
    #         config_name = ctx.params["config_name"]
    #     except (KeyError, AttributeError):
    #         # attribute error occurs when ctx = None
    #         config_name = "maestral"
    #
    #     # get all matching paths in our local Dropbox folder
    #     # TODO: query from server if not too slow
    #
    #     config = MaestralConfig(config_name)
    #     dropbox_dir = config.get("main", "path")
    #     local_incomplete = osp.join(dropbox_dir, incomplete)
    #     local_dirname = osp.dirname(local_incomplete)
    #
    #     if osp.isdir(local_dirname):
    #
    #         with os.scandir(local_dirname) as it:
    #             for entry in it:
    #                 if entry.path.startswith(local_incomplete):
    #                     if entry.is_dir() and self.dir_okay:
    #                         dbx_path = removeprefix(entry.path, dropbox_dir)
    #                         matches.append(dbx_path + "/")
    #                     elif entry.is_file() and self.file_okay:
    #                         dbx_path = removeprefix(entry.path, dropbox_dir)
    #                         matches.append(dbx_path)
    #
    #     # get all matching excluded items
    #
    #     for dbx_path in config.get("main", "excluded_items"):
    #         if dbx_path.startswith("/" + incomplete):
    #             matches.append(dbx_path)
    #
    #     return [CompletionItem(m.lstrip("/")) for m in matches]


class ConfigName(click.ParamType):
    """ "A command line parameter representing a Dropbox path

    :param existing: If ``True`` require an existing config, otherwise create a new
        config on demand.
    """

    name = "config"

    def __init__(self, existing: bool = True) -> None:
        self.existing = existing

    def convert(
        self,
        value: Optional[str],
        param: Optional[click.Parameter],
        ctx: Optional[click.Context],
    ) -> Optional[str]:

        if value is None:
            return value

        from .config import validate_config_name, list_configs

        if not self.existing:

            # accept all valid config names
            try:
                return validate_config_name(value)
            except ValueError:
                raise cli.CliException(
                    "Configuration name may not contain any whitespace"
                )

        else:

            # accept only existing config names
            if value in list_configs():
                return value
            else:
                bv = click.style(value, bold=True)
                bc = click.style("maestral configs", bold=True)

                raise cli.CliException(
                    f"Configuration {bv} does not exist. You can list "
                    f"all existing configurations with {bc}."
                )

    #
    # def shell_complete(
    #     self,
    #     ctx: Optional[click.Context],
    #     param: Optional[click.Parameter],
    #     incomplete: str,
    # ) -> List["CompletionItem"]:
    #
    #     matches = [conf for conf in list_configs() if conf.startswith(incomplete)]
    #     return [CompletionItem(m) for m in matches]
    #


# ======================================================================================
# Command groups
# ======================================================================================


class SpecialHelpOrder(click.Group):
    """Click command group with customizable order of help output."""

    def __init__(self, *args, **kwargs) -> None:
        self.help_priorities: Dict[str, int] = {}
        super(SpecialHelpOrder, self).__init__(*args, **kwargs)

    def get_help(self, ctx: click.Context) -> str:
        self.list_commands = self.list_commands_for_help  # type: ignore
        return super(SpecialHelpOrder, self).get_help(ctx)

    def list_commands_for_help(self, ctx: click.Context) -> Iterable[str]:
        """reorder the list of commands when listing the help"""
        commands = super(SpecialHelpOrder, self).list_commands(ctx)
        return (
            c[1]
            for c in sorted(
                (self.help_priorities.get(command, 1), command) for command in commands
            )
        )

    def command(self, *args, **kwargs) -> Callable:
        """Behaves the same as `click.Group.command()` except capture
        a priority for listing command names in help.
        """
        help_priority = kwargs.pop("help_priority", 1)
        help_priorities = self.help_priorities

        def decorator(f):
            cmd = super(SpecialHelpOrder, self).command(*args, **kwargs)(f)
            help_priorities[cmd.name] = help_priority
            return cmd

        return decorator

    def group(self, *args, **kwargs) -> Callable:
        """Behaves the same as `click.Group.group()` except capture
        a priority for listing command names in help.
        """
        help_priority = kwargs.pop("help_priority", 1)
        help_priorities = self.help_priorities

        def decorator(f):
            cmd = super(SpecialHelpOrder, self).group(*args, **kwargs)(f)
            help_priorities[cmd.name] = help_priority
            return cmd

        return decorator


@click.group(
    cls=SpecialHelpOrder,
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
    no_args_is_help=True,
    help="Maestral Dropbox client for Linux and macOS.",
)
@click.option(
    "--version",
    "-V",
    is_flag=True,
    default=False,
    help="Show version and exit.",
)
def main(version: bool):

    if version:
        click.echo(__version__)


@main.group(
    cls=SpecialHelpOrder, help_priority=14, help="View and manage excluded folders."
)
def excluded():
    pass


@main.group(
    cls=SpecialHelpOrder, help_priority=17, help="Manage desktop notifications."
)
def notify():
    pass


@main.group(cls=SpecialHelpOrder, help_priority=18, help="View and manage the log.")
def log():
    pass


# ======================================================================================
# Main commands
# ======================================================================================

config_option = click.option(
    "-c",
    "--config-name",
    default="maestral",
    type=ConfigName(existing=False),
    is_eager=True,
    expose_value=True,
    help="Run command with the given configuration.",
)

existing_config_option = click.option(
    "-c",
    "--config-name",
    default="maestral",
    type=ConfigName(),
    is_eager=True,
    expose_value=True,
    help="Run command with the given configuration.",
)


@main.command(help_priority=0, help="Run the GUI if installed.")
@config_option
def gui(config_name: str) -> None:

    from packaging.version import Version
    from packaging.requirements import Requirement

    try:
        from importlib.metadata import entry_points, requires, version  # type: ignore
    except ImportError:
        from importlib_metadata import entry_points, requires, version  # type: ignore

    # find all "maestral_gui" entry points registered by other packages
    gui_entry_points = entry_points().get("maestral_gui")

    if not gui_entry_points or len(gui_entry_points) == 0:
        raise cli.CliException(
            "No maestral GUI installed. Please run 'pip3 install maestral[gui]'."
        )

    # check if 1st party defaults "maestral_cocoa" or "maestral_qt" are installed
    default_gui = "maestral_cocoa" if sys.platform == "darwin" else "maestral_qt"
    default_entry_point = next(
        (e for e in gui_entry_points if e.name == default_gui), None
    )

    if default_entry_point:
        # check gui requirements
        requirements = [Requirement(r) for r in requires("maestral")]  # type: ignore

        for r in requirements:
            if r.marker and r.marker.evaluate({"extra": "gui"}):
                version_str = version(r.name)
                if not r.specifier.contains(Version(version_str), prereleases=True):
                    raise cli.CliException(
                        f"{r.name}{r.specifier} required but you have {version_str}"
                    )

        # load entry point
        run = default_entry_point.load()

    else:
        # load any 3rd party GUI
        fallback_entry_point = next(iter(gui_entry_points))
        run = fallback_entry_point.load()

    run(config_name)


@main.command(help_priority=1, help="Start the sync daemon.")
@click.option(
    "--foreground",
    "-f",
    is_flag=True,
    default=False,
    help="Starts Maestral in the foreground.",
)
@click.option(
    "--verbose", "-v", is_flag=True, default=False, help="Print log messages to stdout."
)
@config_option
@catch_maestral_errors
def start(foreground: bool, verbose: bool, config_name: str) -> None:

    # ---- run setup if necessary ------------------------------------------------------

    # We run the setup in the current process. This avoids starting a subprocess despite
    # running with the --foreground flag, prevents leaving a zombie process if the setup
    # fails with an exception and does not confuse systemd.

    from .main import Maestral
    from .daemon import (
        start_maestral_daemon,
        start_maestral_daemon_process,
        is_running,
        Start,
    )

    check_for_updates()

    if is_running(config_name):
        click.echo("Daemon is already running.")
        return

    m = Maestral(config_name, log_to_stdout=verbose)

    if m.pending_link:  # this may raise KeyringAccessError
        link_dialog(m)

    if m.pending_dropbox_folder:
        path = select_dbx_path_dialog(config_name, allow_merge=True)

        while True:
            try:
                m.create_dropbox_directory(path)
                break
            except OSError:
                cli.warn(
                    "Could not create folder. Please make sure that you have "
                    "permissions to write to the selected location or choose a "
                    "different location."
                )

        include_all = cli.confirm("Would you like sync all folders?")

        if not include_all:
            # get all top-level Dropbox folders
            cli.info("Loading...")
            entries = m.list_folder("/", recursive=False)

            names = [
                cast(str, e["name"]) for e in entries if e["type"] == "FolderMetadata"
            ]

            choices = cli.select_multiple(
                "Please choose which top-level folders to include", options=names
            )

            excluded_paths = [
                f"/{name}" for index, name in enumerate(names) if index not in choices
            ]

            m.excluded_items = excluded_paths

    # free resources
    del m

    if foreground:
        # start our current process
        start_maestral_daemon(config_name, log_to_stdout=verbose, start_sync=True)
    else:

        # start daemon process
        cli.echo("Starting Maestral...", nl=False)

        res = start_maestral_daemon_process(
            config_name, log_to_stdout=verbose, start_sync=True
        )

        if res == Start.Ok:
            cli.echo(" " * 8 + OK)
        elif res == Start.AlreadyRunning:
            cli.echo(" " * 8 + "Already running.")
        else:
            cli.echo(" " * 8 + FAILED)
            cli.echo("Please check logs for more information.")


@main.command(help_priority=2, help="Stop the sync daemon.")
@existing_config_option
def stop(config_name: str) -> None:
    stop_daemon_with_cli_feedback(config_name)


@main.command(help_priority=3, help="Restart the sync daemon.")
@click.option(
    "--foreground",
    "-f",
    is_flag=True,
    default=False,
    help="Start the sync daemon in the foreground.",
)
@click.option(
    "--verbose", "-v", is_flag=True, default=False, help="Print log messages to stdout."
)
@existing_config_option
@click.pass_context
def restart(ctx, foreground: bool, verbose: bool, config_name: str) -> None:
    stop_daemon_with_cli_feedback(config_name)
    ctx.forward(start)


@main.command(
    help_priority=4,
    help="""
Automatically start the sync daemon on login.

A systemd or launchd service will be created to start a sync daemon for the given
configuration on user login.
""",
)
@click.option("--yes", "-Y", is_flag=True, default=False)
@click.option("--no", "-N", is_flag=True, default=False)
@existing_config_option
def autostart(yes: bool, no: bool, config_name: str) -> None:

    from .autostart import AutoStart

    auto_start = AutoStart(config_name)

    if not auto_start.implementation:
        cli.echo(
            "Autostart is currently not supported for your platform.\n"
            "Autostart requires systemd on Linux or launchd on macOS."
        )
        return

    if yes or no:
        if yes:
            auto_start.enable()
            cli.ok("Enabled start on login.")
        else:
            auto_start.disable()
            cli.ok("Disabled start on login.")
    else:
        if auto_start.enabled:
            cli.echo("Autostart is enabled. Use -N to disable.")
        else:
            cli.echo("Autostart is disabled. Use -Y to enable.")


@main.command(help_priority=5, help="Pause syncing.")
@existing_config_option
def pause(config_name: str) -> None:

    from .daemon import MaestralProxy

    try:
        with MaestralProxy(config_name) as m:
            m.pause_sync()
        cli.ok("Syncing paused.")
    except Pyro5.errors.CommunicationError:
        cli.echo("Maestral daemon is not running.")


@main.command(help_priority=6, help="Resume syncing.")
@existing_config_option
def resume(config_name: str) -> None:
    from .daemon import MaestralProxy

    try:
        with MaestralProxy(config_name) as m:
            if not check_for_fatal_errors(m):
                m.resume_sync()
                cli.ok("Syncing resumed.")

    except Pyro5.errors.CommunicationError:
        cli.echo("Maestral daemon is not running.")


@main.command(help_priority=7, help="Show the status of the daemon.")
@existing_config_option
@catch_maestral_errors
def status(config_name: str) -> None:

    from .daemon import MaestralProxy

    check_for_updates()

    try:
        with MaestralProxy(config_name) as m:

            n_errors = len(m.sync_errors)
            color = "red" if n_errors > 0 else "green"
            n_errors_str = click.style(str(n_errors), fg=color)
            cli.echo("")
            cli.echo("Account:      {}".format(m.get_state("account", "email")))
            cli.echo("Usage:        {}".format(m.get_state("account", "usage")))
            cli.echo("Status:       {}".format(m.status))
            cli.echo("Sync threads: {}".format("Running" if m.running else "Stopped"))
            cli.echo("Sync errors:  {}".format(n_errors_str))
            cli.echo("")

            check_for_fatal_errors(m)

            sync_errors = m.sync_errors

            if len(sync_errors) > 0:

                path_column = cli.Column(title="Path")
                message_column = cli.Column(title="Error", wraps=True)

                for error in sync_errors:
                    path_column.append(error["dbx_path"])
                    message_column.append("{title}. {message}".format(**error))

                table = cli.Table([path_column, message_column])

                table.echo()
                cli.echo("")

    except Pyro5.errors.CommunicationError:
        cli.echo("Maestral daemon is not running.")


@main.command(
    help_priority=8,
    help="""
Show the sync status of a file or folder.

Returned value will be 'uploading', 'downloading', 'up to date', 'error', or
'unwatched' (for files outside of the Dropbox directory). This will always be
'unwatched' if syncing is paused.
""",
)
@click.argument("local_path", type=click.Path(exists=True, resolve_path=True))
@existing_config_option
def file_status(local_path: str, config_name: str) -> None:

    from .daemon import MaestralProxy

    try:
        with MaestralProxy(config_name) as m:
            stat = m.get_file_status(local_path)
            cli.echo(stat)

    except Pyro5.errors.CommunicationError:
        cli.echo("unwatched")


@main.command(help_priority=9, help="Live view of all items being synced.")
@existing_config_option
@catch_maestral_errors
def activity(config_name: str) -> None:

    import curses
    from .utils import natural_size
    from .daemon import MaestralProxy

    try:
        with MaestralProxy(config_name) as m:

            if check_for_fatal_errors(m):
                return

            def curses_loop(screen) -> None:  # no type hints for screen provided yet

                curses.use_default_colors()  # don't change terminal background
                screen.nodelay(1)  # sets `screen.getch()` to non-blocking

                while True:

                    height, width = screen.getmaxyx()

                    # create header
                    lines = [f"Status: {m.status}, Sync errors: {len(m.sync_errors)}"]
                    lines.append("")

                    # create table
                    filenames = ["Path"]
                    states = ["Status"]
                    col_len = 4

                    for event in m.get_activity(limit=height - 3):

                        dbx_path = cast(str, event["dbx_path"])
                        direction = cast(str, event["direction"])
                        state = cast(str, event["status"])
                        size = cast(int, event["size"])
                        completed = cast(int, event["completed"])

                        filename = os.path.basename(dbx_path)
                        filenames.append(filename)

                        arrow = "↓" if direction == "down" else "↑"

                        if completed > 0:
                            done_str = natural_size(completed, sep=False)
                            todo_str = natural_size(size, sep=False)
                            states.append(f"{done_str}/{todo_str} {arrow}")
                        else:
                            if state == "syncing" and direction == "up":
                                states.append("uploading")
                            elif state == "syncing" and direction == "down":
                                states.append("downloading")
                            else:
                                states.append(state)

                        col_len = max(len(filename), col_len)

                    for name, state in zip(filenames, states):  # create rows
                        lines.append(name.ljust(col_len + 2) + state)

                    # print to console screen
                    screen.clear()
                    try:
                        screen.addstr("\n".join(lines))
                    except curses.error:
                        pass
                    screen.refresh()

                    # abort when user presses 'q', refresh otherwise
                    key = screen.getch()
                    if key == ord("q"):
                        break
                    elif key < 0:
                        time.sleep(1)

            # enter curses event loop
            curses.wrapper(curses_loop)

    except Pyro5.errors.CommunicationError:
        cli.echo("Maestral daemon is not running.")


@main.command(help_priority=10, help="List contents of a Dropbox directory.")
@click.argument("dropbox_path", type=click.Path(), default="")
@click.option(
    "-l",
    "--long",
    is_flag=True,
    default=False,
    help="Show output in long format with metadata.",
)
@click.option(
    "-d",
    "--include-deleted",
    is_flag=True,
    default=False,
    help="Include deleted items in listing.",
)
@existing_config_option
@catch_maestral_errors
def ls(long: bool, dropbox_path: str, include_deleted: bool, config_name: str) -> None:

    from datetime import datetime
    from .utils import natural_size
    from .daemon import MaestralProxy

    if not dropbox_path.startswith("/"):
        dropbox_path = "/" + dropbox_path

    with MaestralProxy(config_name, fallback=True) as m:

        cli.echo("Loading...\r", nl=False)

        entries = m.list_folder(
            dropbox_path,
            recursive=False,
            include_deleted=include_deleted,
        )
        entries.sort(key=lambda x: cast(str, x["name"]).lower())

        if long:

            to_short_type = {
                "FileMetadata": "file",
                "FolderMetadata": "folder",
                "DeletedMetadata": "deleted",
            }

            table = cli.Table(
                columns=[
                    cli.Column("Name"),
                    cli.Column("Type"),
                    cli.Column("Size", align=cli.Align.Right),
                    cli.Column("Shared"),
                    cli.Column("Syncing"),
                    cli.Column("Last Modified"),
                ]
            )

            for entry in entries:

                item_type = to_short_type[cast(str, entry["type"])]
                name = cast(str, entry["name"])
                path_lower = cast(str, entry["path_lower"])

                text = "shared" if "sharing_info" in entry else "private"
                color = "bright_black" if text == "private" else None
                shared_field = cli.TextField(text, fg=color)

                excluded_status = m.excluded_status(path_lower)
                color = "green" if excluded_status == "included" else None
                text = "✓" if excluded_status == "included" else excluded_status
                excluded_field = cli.TextField(text, fg=color)

                if "size" in entry:
                    size = natural_size(cast(float, entry["size"]))
                else:
                    size = "-"

                dt_field: cli.Field

                if "client_modified" in entry:
                    cm = cast(str, entry["client_modified"])
                    dt = datetime.strptime(cm, "%Y-%m-%dT%H:%M:%S%z").astimezone()
                    dt_field = cli.DateField(dt)
                else:
                    dt_field = cli.TextField("-")

                table.append(
                    [name, item_type, size, shared_field, excluded_field, dt_field]
                )

            cli.echo(" " * 15)
            table.echo()
            cli.echo(" " * 15)

        else:

            grid = cli.Grid()

            for entry in entries:
                name = cast(str, entry["name"])
                color = "blue" if entry["type"] == "DeletedMetadata" else None

                grid.append(cli.TextField(name, fg=color))

            grid.echo()


@main.command(help_priority=11, help="Link with a Dropbox account.")
@click.option(
    "-r",
    "relink",
    is_flag=True,
    default=False,
    help="Relink to the current account. Keeps the sync state.",
)
@config_option
@catch_maestral_errors
def link(relink: bool, config_name: str) -> None:
    from .daemon import MaestralProxy

    with MaestralProxy(config_name, fallback=True) as m:

        if m.pending_link or relink:
            link_dialog(m)
        else:
            cli.echo(
                "Maestral is already linked. Use the option "
                "'-r' to relink to the same account."
            )


@main.command(
    help_priority=12,
    help="""
Unlinks your Dropbox account.

If Maestral is running, it will be stopped before unlinking.
""",
)
@existing_config_option
@catch_maestral_errors
def unlink(config_name: str) -> None:

    if cli.confirm("Are you sure you want unlink your account?", default=False):

        from .main import Maestral

        stop_daemon_with_cli_feedback(config_name)
        m = Maestral(config_name)
        m.unlink()

        cli.ok("Unlinked Maestral.")


@main.command(help_priority=13, help="Change the location of the local Dropbox folder.")
@click.argument("new_path", required=False, type=click.Path(writable=True))
@existing_config_option
def move_dir(new_path: str, config_name: str) -> None:
    from .daemon import MaestralProxy

    new_path = new_path or select_dbx_path_dialog(config_name)

    with MaestralProxy(config_name, fallback=True) as m:
        m.move_dropbox_directory(new_path)

    cli.ok(f"Dropbox folder moved to {new_path}.")


@main.command(
    help_priority=15,
    help="""
Rebuild the sync index.

Rebuilding may take several minutes, depending on the size of your Dropbox.
""",
)
@existing_config_option
@catch_maestral_errors
def rebuild_index(config_name: str) -> None:

    import textwrap
    from .daemon import MaestralProxy

    with MaestralProxy(config_name, fallback=True) as m:

        width, height = click.get_terminal_size()

        msg = textwrap.fill(
            "Rebuilding the index may take several minutes, depending on the size of "
            "your Dropbox. Any changes to local files will be synced once rebuilding "
            "has completed. If you stop the daemon during the process, rebuilding will "
            "start again on the next launch.\nIf the daemon is not currently running, "
            "a rebuild will be schedules for the next startup.",
            width=width,
        )

        cli.echo(msg + "\n")

        if cli.confirm("Do you want to continue?", default=False):

            m.rebuild_index()

            status_command = click.style("maestral status", bold=True)

            if m._is_fallback:
                cli.ok(f"Rebuilding now. Run {status_command} to view progress.")
            else:
                cli.ok("Daemon is not running. Rebuilding scheduled for next startup.")


@main.command(
    help_priority=16,
    help="""
Restore a previous version of a file.

If no revision number is given, old revisions will be listed.
""",
)
@click.argument("dropbox_path", type=click.Path())
@click.option("-v", "--rev", help="Revision to restore", default="")
@existing_config_option
@catch_maestral_errors
def restore(dropbox_path: str, rev: str, config_name: str) -> None:
    from datetime import datetime
    from .daemon import MaestralProxy

    if not dropbox_path.startswith("/"):
        dropbox_path = "/" + dropbox_path

    with MaestralProxy(config_name, fallback=True) as m:

        if not rev:
            cli.echo("Loading...\r", nl=False)
            entries = m.list_revisions(dropbox_path)
            dates = []
            for entry in entries:
                cm = cast(str, entry["client_modified"])
                dt = datetime.strptime(cm, "%Y-%m-%dT%H:%M:%S%z").astimezone()
                field = cli.DateField(dt)
                dates.append(field.format(40)[0])

            index = cli.select(
                message="Select a version to restore:",
                options=dates,
                hint="(↓ to see more)" if len(entries) > 6 else "",
            )
            rev = cast(str, entries[index]["rev"])

        m.restore(dropbox_path, rev)

    cli.ok(f'Restored {rev} to "{dropbox_path}"')


@main.command(help_priority=17, help="Show recently changed or added files.")
@existing_config_option
def history(config_name: str) -> None:

    from datetime import datetime
    from .daemon import MaestralProxy

    with MaestralProxy(config_name, fallback=True) as m:
        history = m.get_history()

    table = cli.Table(
        [
            cli.Column("Path", elide=cli.Elide.Leading),
            cli.Column("Change"),
            cli.Column("Time"),
        ]
    )

    for event in history:

        dbx_path = cast(str, event["dbx_path"])
        change_type = cast(str, event["change_type"])
        change_time_or_sync_time = cast(float, event["change_time_or_sync_time"])
        dt = datetime.fromtimestamp(change_time_or_sync_time)

        table.append([dbx_path, change_type, dt])

    cli.echo("")
    table.echo()
    cli.echo("")


@main.command(help_priority=18, help="List all configured Dropbox accounts.")
def configs() -> None:

    from .daemon import is_running
    from .config import (
        MaestralConfig,
        MaestralState,
        list_configs,
        remove_configuration,
    )

    # clean up stale configs
    config_names = list_configs()

    for name in config_names:
        dbid = MaestralConfig(name).get("account", "account_id")
        if dbid == "" and not is_running(name):
            remove_configuration(name)

    # display remaining configs
    names = list_configs()
    emails = [MaestralState(c).get("account", "email") for c in names]

    table = cli.Table([cli.Column("Config name", names), cli.Column("Account", emails)])

    cli.echo("")
    table.echo()
    cli.echo("")


@main.command(
    help_priority=20,
    help="""
Enable or disables sharing of error reports.

Sharing is disabled by default. If enabled, error reports are shared with bugsnag and no
personal information will typically be collected. Shared tracebacks may however include
file names, depending on the error.
""",
)
@click.option("--yes", "-Y", is_flag=True, default=False)
@click.option("--no", "-N", is_flag=True, default=False)
@existing_config_option
def analytics(yes: bool, no: bool, config_name: str) -> None:
    from .daemon import MaestralProxy

    if yes or no:
        with MaestralProxy(config_name, fallback=True) as m:
            m.analytics = yes

        status_str = "Enabled" if yes else "Disabled"
        cli.ok(f"{status_str} automatic error reports.")
    else:
        with MaestralProxy(config_name, fallback=True) as m:
            enabled = m.analytics

        if enabled:
            cli.echo("Analytics are enabled. Use -N to disable")
        else:
            cli.echo("Analytics are disabled. Use -Y to enable")


@main.command(help_priority=22, help="Show linked Dropbox account information.")
@existing_config_option
def account_info(config_name: str) -> None:
    from .daemon import MaestralProxy

    with MaestralProxy(config_name, fallback=True) as m:

        email = m.get_state("account", "email")
        account_type = m.get_state("account", "type").capitalize()
        usage = m.get_state("account", "usage")
        dbid = m.get_conf("account", "account_id")

    cli.echo("")
    cli.echo(f"Email:         {email}")
    cli.echo(f"Account-type:  {account_type}")
    cli.echo(f"Usage:         {usage}")
    cli.echo(f"Dropbox-ID:    {dbid}")
    cli.echo("")


@main.command(help_priority=23, help="Return the version number and other information.")
def about() -> None:

    year = time.localtime().tm_year

    cli.echo("")
    cli.echo(f"Version:    {__version__}")
    cli.echo(f"Website:    {__url__}")
    cli.echo(f"Copyright:  (c) 2018-{year}, {__author__}.")
    cli.echo("")


# ======================================================================================
# Exclude commands
# ======================================================================================


@excluded.command(
    name="list", help_priority=0, help="List all excluded files and folders."
)
@existing_config_option
def excluded_list(config_name: str) -> None:
    from .daemon import MaestralProxy

    with MaestralProxy(config_name, fallback=True) as m:

        excluded_items = m.excluded_items
        excluded_items.sort()

        if len(excluded_items) == 0:
            cli.echo("No excluded files or folders.")
        else:
            for item in excluded_items:
                cli.echo(item)


@excluded.command(
    name="add",
    help_priority=1,
    help="Add a file or folder to the excluded list and re-sync.",
)
@click.argument("dropbox_path", type=click.Path())
@existing_config_option
@catch_maestral_errors
def excluded_add(dropbox_path: str, config_name: str) -> None:
    from .daemon import MaestralProxy

    if not dropbox_path.startswith("/"):
        dropbox_path = "/" + dropbox_path

    if dropbox_path == "/":
        raise cli.CliException("Cannot exclude the root directory.")

    with MaestralProxy(config_name, fallback=True) as m:
        m.exclude_item(dropbox_path)
        path_str = click.style(dropbox_path, bold=True)
        cli.ok(f"Excluded {path_str}.")


@excluded.command(
    name="remove",
    help_priority=2,
    help="Remove a file or folder from the excluded list and re-sync.",
)
@click.argument("dropbox_path", type=click.Path())
@existing_config_option
@catch_maestral_errors
def excluded_remove(dropbox_path: str, config_name: str) -> None:
    from .daemon import MaestralProxy

    if not dropbox_path.startswith("/"):
        dropbox_path = "/" + dropbox_path

    if dropbox_path == "/":
        return cli.echo("The root directory is always included")

    try:
        with MaestralProxy(config_name) as m:
            m.include_item(dropbox_path)
            path_str = click.style(dropbox_path, bold=True)
            cli.ok(f"Included {path_str}. Now downloading...")

    except Pyro5.errors.CommunicationError:
        raise cli.CliException("Daemon must be running to download folders.")


# ======================================================================================
# Log commands
# ======================================================================================


@log.command(name="show", help_priority=0, help="Print logs to the console.")
@click.option(
    "--external", "-e", is_flag=True, default=False, help="Open in external program."
)
@existing_config_option
def log_show(external: bool, config_name: str) -> None:

    from .utils.appdirs import get_log_path

    log_file = get_log_path("maestral", config_name + ".log")

    if external:
        res = click.launch(log_file)
    else:
        try:
            with open(log_file) as f:
                text = f.read()
            click.echo_via_pager(text)
        except OSError:
            res = 1
        else:
            res = 0

    if res > 0:
        raise cli.CliException(f"Could not open log file at '{log_file}'")


@log.command(name="clear", help_priority=1, help="Clear the log files.")
@existing_config_option
def log_clear(config_name: str) -> None:

    from .utils.appdirs import get_log_path

    log_dir = get_log_path("maestral")
    log_name = config_name + ".log"

    log_files = []

    for file_name in os.listdir(log_dir):
        if file_name.startswith(log_name):
            log_files.append(os.path.join(log_dir, file_name))

    try:
        for file in log_files:
            open(file, "w").close()
        cli.ok("Cleared log files.")
    except FileNotFoundError:
        cli.ok("Cleared log files.")
    except OSError:
        raise cli.CliException(
            f"Could not clear log at '{log_dir}'. " f"Please try to delete it manually"
        )


@log.command(name="level", help_priority=2, help="Get or set the log level.")
@click.argument(
    "level_name",
    required=False,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
)
@existing_config_option
def log_level(level_name: str, config_name: str) -> None:

    import logging
    from .daemon import MaestralProxy

    with MaestralProxy(config_name, fallback=True) as m:
        if level_name:
            m.log_level = cast(int, getattr(logging, level_name))
            cli.ok(f"Log level set to {level_name}.")
        else:
            level_name = logging.getLevelName(m.log_level)
            cli.echo(f"Log level: {level_name}")


# ======================================================================================
# Notification commands
# ======================================================================================


@notify.command(
    name="level",
    help_priority=0,
    help="Get or set the level for desktop notifications.",
)
@click.argument(
    "level_name",
    required=False,
    type=click.Choice(["ERROR", "SYNCISSUE", "FILECHANGE"]),
)
@existing_config_option
def notify_level(level_name: str, config_name: str) -> None:

    from .notify import MaestralDesktopNotifier as Notifier
    from .daemon import MaestralProxy

    with MaestralProxy(config_name, fallback=True) as m:
        if level_name:
            m.notification_level = Notifier.level_name_to_number(level_name)
            cli.ok(f"Notification level set to {level_name}.")
        else:
            level_name = Notifier.level_number_to_name(m.notification_level)
            cli.echo(f"Notification level: {level_name}.")


@notify.command(
    name="snooze",
    help_priority=1,
    help="Snooze desktop notifications of file changes.",
)
@click.argument("minutes", type=click.IntRange(min=0))
@existing_config_option
def notify_snooze(minutes: int, config_name: str) -> None:
    from .daemon import MaestralProxy

    try:
        with MaestralProxy(config_name) as m:
            m.notification_snooze = minutes
    except Pyro5.errors.CommunicationError:
        cli.echo("Maestral daemon is not running.")
    else:
        if minutes > 0:
            cli.ok(
                f"Notifications snoozed for {minutes} min. " "Set snooze to 0 to reset."
            )
        else:
            cli.ok("Notifications enabled.")
