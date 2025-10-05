#!/usr/bin/env python3
"""Object oriented Gaussian job submission helper.

This module is a faithful, yet fully object-oriented, port of the legacy bash
script used to submit Gaussian jobs on the HPC cluster.  The rewrite keeps the
behaviour and CLI surface compatible with the original workflow while splitting
the responsibilities across a small set of focused classes.  The result is code
that is easier to reason about, extend and test.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------------------
# Terminal colours (mirroring the bash implementation)
# --------------------------------------------------------------------------------------

RED = "\033[0;31m"
NC = "\033[m"
YELLOW = "\033[1;33m"
BLUE = "\033[1;34m"


# --------------------------------------------------------------------------------------
# Usage text
# --------------------------------------------------------------------------------------


USAGE_TEXT = textwrap.dedent(
    f"""
    gaussian function v1.2

    {RED}NAME{NC}
            gfunc


    {RED}SYNOPSIS{NC}
            gf [jobfilename.com]
            gf --queue pqph --memory 48GB file1.com file2.com


    {RED}OPTIONS{NC}
            {BLUE}-q{NC}, {BLUE}--queue{NC} [cue]
                    set the cue for the job, default is pqph
            {BLUE}-c{NC}, {BLUE}--cores{NC} [cores]
                    sets the number of cores, 8 is set as default
            {BLUE}-m{NC}, {BLUE}--memory{NC} [memory]
                    sets the quantity of memory to use (MB or GB)
            {BLUE}-w{NC}, {BLUE}--walltime{NC} [walltime]
                    set the walltime
            {BLUE}-g{NC}, {BLUE}--gaussian-version{NC} [gaussian version]
                    sets the version of gaussian in use (e.g. d01)
            {BLUE}-s{NC}, {BLUE}--quiet{NC}
                    send directly the job (default behaviour)
            {BLUE}-i{NC}, {BLUE}--prompt{NC}
                    review the input interactively before submission
            {BLUE}-p{NC}, {BLUE}--preset{NC} [preset]
                    preset =
                            [0-9]   load a preset
                            show    list the saved preset
                            set     open the editor to set the preset
            {BLUE}-d{NC}, {BLUE}--maxdisk{NC} [max disk]
                    set the maxdisk
            {BLUE}-n{NC}, {BLUE}--no-correction{NC}
                    no correction of the input file
            {BLUE}-f{NC}, {BLUE}--force{NC}
                    submit with priority (qsub -p 100)
            {BLUE}-l{NC}, {BLUE}--logs{NC} [select]
                    select =
                            all
                            work ID (e.g. '7197851')
                    prints the log of the jobs sent
            {BLUE}-r{NC}, {BLUE}--dry-run{NC}
                    show the qsub command instead of submitting
            {BLUE}--show-summary{NC}
                    print a short job overview even in quiet mode
            {BLUE}-h{NC}, {BLUE}--help{NC}
                    help

    {RED}DESCRIPTION{NC}
    This function sends the jobs to the HPC.
    It also corrects the settings of your file automatically.
    In the input file the checkpoint filename is set equally to the input filename,
    the number of cores is set coherently to the input as the memory. This automatic
    correction can be disabled by -n option
    This function relies on a modified version of a script files given me by Claire
    (thanks Claire) that have to be placed in  ~/bin.
    Next function that is projected to be added is the correction of the input file
    settings even if they are not written at all in the input file.
    Enjoy!!
    """
)


def print_usage() -> None:
    """Display the historical usage text."""

    print(USAGE_TEXT)


# --------------------------------------------------------------------------------------
# Path and settings dataclasses
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Paths:
    """Collection of filesystem locations used by the helper."""

    bin_dir: Path = Path.home() / "bin"
    script_file: Path = Path.home() / "bin" / ".rng"
    presets_file: Path = Path.home() / "bin" / ".presets"
    log_file: Path = Path.home() / "bin" / ".wlog"
    full_log_file: Path = Path.home() / "bin" / ".wulog"

    def ensure_support_files(self) -> None:
        """Ensure directories and default helper files exist."""

        self.bin_dir.mkdir(parents=True, exist_ok=True)
        if not self.script_file.exists():
            self.script_file.write_text(DEFAULT_SCRIPT_TEMPLATE)
            self.script_file.chmod(0o755)
        if not self.presets_file.exists():
            self.presets_file.write_text(DEFAULT_PRESET_TEMPLATE)
        for target in (self.log_file, self.full_log_file):
            if not target.exists():
                target.touch()


@dataclass(frozen=True)
class SubmitSettings:
    """Mutable job configuration shared across the workflow."""

    queue: str = "pqph"
    cores: int = 12
    memory_mb: int = 47988
    walltime: str = "119:59:00"
    gaussian_version: Optional[str] = None
    quiet: bool = True
    force_priority: bool = False
    correction_enabled: bool = True
    maxdisk_mb: Optional[int] = None
    preset_loaded: Optional[int] = None
    dry_run: bool = False
    show_summary: bool = False
    whitestripes: str = ""

    def summary(self) -> str:
        parts = [
            f"Cores: {self.cores}",
            f"Memory: {UnitParser.format_mb(self.memory_mb)}",
            f"Cue: {self.queue}",
            f"Walltime: {self.walltime}",
        ]
        if self.gaussian_version:
            parts.append(f"Gaussian-version: {self.gaussian_version}")
        if self.maxdisk_mb is not None:
            parts.append(f"Maxdisk: {UnitParser.format_mb(self.maxdisk_mb)}")
        return "; ".join(parts)

    def update_from_preset(self, preset_number: int, preset: Preset) -> "SubmitSettings":
        updated = replace(
            self,
            queue=preset.queue or self.queue,
            cores=preset.cores or self.cores,
            memory_mb=preset.memory_mb or self.memory_mb,
            walltime=preset.walltime or self.walltime,
            gaussian_version=preset.gaussian_version,
            maxdisk_mb=preset.maxdisk_mb,
            preset_loaded=preset_number,
        )
        formatted_maxdisk = (
            UnitParser.format_mb(updated.maxdisk_mb) if updated.maxdisk_mb is not None else ""
        )
        whitestripes = (
            f"Charged preset : {updated.queue} {updated.cores} "
            f"{UnitParser.format_mb(updated.memory_mb)} {updated.walltime} "
            f"{updated.gaussian_version or ''} {formatted_maxdisk}"
        ).strip()
        return replace(updated, whitestripes=whitestripes)

    def with_updates(self, **changes) -> "SubmitSettings":
        return replace(self, **changes)


# --------------------------------------------------------------------------------------
# Utility helpers
# --------------------------------------------------------------------------------------


class UnitParser:
    """Parse and format storage units consistently."""

    @staticmethod
    def parse_to_mb(value: Optional[str], default: Optional[int] = None) -> Optional[int]:
        if value is None:
            return default
        stripped = value.strip()
        if not stripped:
            return default
        upper = stripped.upper()
        suffixes = {"MB": 1, "GB": 1000}
        for suffix, multiplier in suffixes.items():
            if upper.endswith(suffix):
                number = upper[: -len(suffix)]
                try:
                    return int(number) * multiplier
                except ValueError as exc:
                    raise ValueError(f"Invalid numeric value for {suffix}: {value}") from exc
        try:
            return int(upper)
        except ValueError as exc:
            raise ValueError(f"Could not parse size specification: {value}") from exc

    @staticmethod
    def format_mb(value: int) -> str:
        if value % 1000 == 0:
            return f"{value // 1000}GB"
        return f"{value}MB"


# --------------------------------------------------------------------------------------
# Preset management
# --------------------------------------------------------------------------------------


@dataclass
class Preset:
    queue: str
    cores: int
    memory_mb: int
    walltime: str
    gaussian_version: Optional[str]
    maxdisk_mb: Optional[int]

    @classmethod
    def from_line(cls, line: str) -> "Preset":
        parts = [segment.strip() for segment in line.split(";")]
        if len(parts) != 6:
            raise ValueError("Preset line must contain exactly six fields")
        queue, cores, memory, walltime, version, maxdisk = parts
        return cls(
            queue=queue,
            cores=int(cores),
            memory_mb=UnitParser.parse_to_mb(memory, None) or 0,
            walltime=walltime,
            gaussian_version=version or None,
            maxdisk_mb=UnitParser.parse_to_mb(maxdisk, None),
        )

    def to_line(self) -> str:
        maxdisk = UnitParser.format_mb(self.maxdisk_mb) if self.maxdisk_mb is not None else ""
        return ";".join(
            [
                self.queue,
                str(self.cores),
                UnitParser.format_mb(self.memory_mb),
                self.walltime,
                self.gaussian_version or "",
                maxdisk,
            ]
        )


class PresetManager:
    """Read and update preset definitions."""

    def __init__(self, paths: Paths) -> None:
        self.paths = paths

    def iter_presets(self) -> Iterable[Tuple[int, Preset]]:
        with self.paths.presets_file.open() as handle:
            sequence_index = 1
            for _, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line or line.startswith("##"):
                    continue
                try:
                    yield sequence_index, Preset.from_line(line)
                    sequence_index += 1
                except ValueError:
                    continue

    def show_presets(self) -> None:
        for idx, preset in self.iter_presets():
            maxdisk = (
                UnitParser.format_mb(preset.maxdisk_mb)
                if preset.maxdisk_mb is not None
                else ""
            )
            print(
                f"{idx} - cue: {preset.queue} cores:{preset.cores} memory: {UnitParser.format_mb(preset.memory_mb)} "
                f"walltime: {preset.walltime} gaussian version: {preset.gaussian_version or ''} max disk: {maxdisk}"
            )

    def open_editor(self) -> None:
        editor = os.environ.get("EDITOR", "vi")
        subprocess.call([editor, str(self.paths.presets_file)])

    def get_preset(self, preset_number: int) -> Preset:
        presets = list(self.iter_presets())
        if preset_number < 1 or preset_number > len(presets):
            raise ValueError(f"Preset {preset_number} not found")
        _, preset = presets[preset_number - 1]
        return preset


# --------------------------------------------------------------------------------------
# Gaussian input correction
# --------------------------------------------------------------------------------------


class GaussianInputCorrector:
    """Apply the input file adjustments previously performed via sed."""

    def correct(self, path: Path, settings: SubmitSettings) -> None:
        if not settings.correction_enabled:
            return
        if not path.exists():
            return

        lines = path.read_text().splitlines()

        def update_directive(keyword: str, replacement: str, default_index: int) -> None:
            lowered = keyword.lower()
            for idx, line in enumerate(lines):
                if line.strip().lower().startswith(lowered):
                    lines[idx] = replacement
                    return
            lines.insert(default_index, replacement)

        gm = (settings.memory_mb * 15) // 20
        update_directive("%mem", f"%mem={gm}MB", 0)
        update_directive("%nprocshared", f"%nprocshared={settings.cores}", 1)
        update_directive("%chk", f"%chk={path.stem}.chk", 2)

        if settings.maxdisk_mb is not None:
            keyword = "maxdisk"
            replacement = f"maxdisk={settings.maxdisk_mb}MB"
            lowered = keyword.lower()
            for idx, line in enumerate(lines):
                if line.strip().lower().startswith(lowered):
                    lines[idx] = replacement
                    break
            else:
                lines.append(replacement)

        path.write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------------------
# PBS helper script management
# --------------------------------------------------------------------------------------


class PBSScriptManager:
    """Update the submission helper script based on the active settings."""

    def __init__(self, paths: Paths) -> None:
        self.paths = paths

    def update(self, settings: SubmitSettings) -> None:
        content = self.paths.script_file.read_text().splitlines()

        def replace_line(predicate, replacement, insert_index: Optional[int] = None) -> None:
            for idx, line in enumerate(content):
                if predicate(line):
                    content[idx] = replacement
                    return
            if insert_index is not None:
                content.insert(insert_index, replacement)
            else:
                content.append(replacement)

        if settings.maxdisk_mb is not None:
            resources = (
                f"#PBS -lselect=1:ncpus={settings.cores}:mem={settings.memory_mb}MB:tmpspace={settings.maxdisk_mb}MB"
            )
        else:
            resources = f"#PBS -lselect=1:ncpus={settings.cores}:mem={settings.memory_mb}MB"
        replace_line(lambda line: line.strip().startswith("#PBS -lselect=1:ncpus="), resources)
        replace_line(
            lambda line: line.strip().startswith("#PBS -l walltime="),
            f"#PBS -l walltime={settings.walltime}",
        )

        if settings.queue.upper() != "PUBLIC":
            replace_line(
                lambda line: line.strip().startswith("#PBS -q "),
                f"#PBS -q {settings.queue}",
                insert_index=13,
            )
        else:
            content = [line for line in content if not line.strip().startswith("#PBS -q ")]

        if settings.gaussian_version:
            replace_line(
                lambda line: line.strip().startswith("module load gaussian/"),
                f"module load gaussian/g09-{settings.gaussian_version}",
            )

        self.paths.script_file.write_text("\n".join(content) + "\n")


# --------------------------------------------------------------------------------------
# Scheduler abstraction
# --------------------------------------------------------------------------------------


@dataclass
class SubmissionResult:
    succeeded: bool
    output: str


class Scheduler(ABC):
    @abstractmethod
    def submit(self, command: Sequence[str]) -> SubmissionResult:
        raise NotImplementedError


class PBSScheduler(Scheduler):
    """Execute qsub commands."""

    def submit(self, command: Sequence[str]) -> SubmissionResult:
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True)
        except FileNotFoundError:
            return SubmissionResult(False, "qsub command not found. Please ensure the PBS client tools are installed.")

        output = (result.stdout or result.stderr or "").strip()
        return SubmissionResult(result.returncode == 0, output)


# --------------------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------------------


class JobLogger:
    def __init__(self, paths: Paths) -> None:
        self.paths = paths

    def append(self, message: str) -> None:
        for log in (self.paths.log_file, self.paths.full_log_file):
            with log.open("a") as handle:
                handle.write(message + "\n")

    def log_line(self, qsub_output: str, job_name: str) -> str:
        timestamp = datetime.utcnow().strftime("%d/%m - %H:%M")
        work_dir = str(Path.cwd())
        prefix = "/work/gd2613/jobs/"
        if work_dir.startswith(prefix):
            work_dir = work_dir[len(prefix) :]
        return f"{timestamp} | {qsub_output} | {job_name} | {work_dir}"

    def show(self, selector: str) -> None:
        selector = selector.strip()
        if selector.lower() == "all":
            print(self.paths.log_file.read_text())
            return
        matches = []
        with self.paths.log_file.open() as handle:
            for line in handle:
                if selector in line:
                    matches.append(line.rstrip())
        print("\n".join(matches))


# --------------------------------------------------------------------------------------
# CLI parsing (mirrors original getopts behaviour)
# --------------------------------------------------------------------------------------


@dataclass
class CLIResult:
    files: List[str]
    settings: SubmitSettings


class GaussianJobCLI:
    def __init__(
        self,
        preset_manager: PresetManager,
        logger: JobLogger,
    ) -> None:
        self.preset_manager = preset_manager
        self.logger = logger

    def parse(self, argv: Sequence[str], initial_settings: SubmitSettings) -> CLIResult:
        settings = initial_settings
        files: List[str] = []
        argc = len(argv)
        i = 0

        def fail(message: str) -> None:
            print(message, file=sys.stderr)
            sys.exit(1)

        def take_value(option: str, inline: Optional[str]) -> str:
            nonlocal i
            if inline is not None:
                if inline == "":
                    fail(f"Missing argument for option {option}")
                i += 1
                return inline
            if i + 1 >= argc:
                fail(f"Missing argument for option {option}")
            value = argv[i + 1]
            i += 2
            return value

        while i < argc:
            arg = argv[i]

            if arg == "--":
                files.extend(argv[i + 1 :])
                break
            if not arg.startswith("-") or arg == "-":
                files.append(arg)
                i += 1
                continue

            if arg.startswith("--"):
                name, eq, inline_value = arg.partition("=")
                inline = inline_value if eq else None

                if name in ("--help",):
                    print_usage()
                    sys.exit(0)
                if name == "--quiet":
                    settings = settings.with_updates(quiet=True)
                    i += 1
                    continue
                if name in ("--prompt", "--interactive"):
                    settings = settings.with_updates(quiet=False, show_summary=True)
                    i += 1
                    continue
                if name == "--dry-run":
                    settings = settings.with_updates(dry_run=True, show_summary=True)
                    i += 1
                    continue
                if name == "--show-summary":
                    settings = settings.with_updates(show_summary=True)
                    i += 1
                    continue
                if name == "--no-correction":
                    settings = settings.with_updates(correction_enabled=False)
                    i += 1
                    continue
                if name == "--force":
                    settings = settings.with_updates(force_priority=True)
                    i += 1
                    continue
                if name == "--logs":
                    selector = take_value(name, inline)
                    self.logger.show(selector)
                    sys.exit(0)
                if name in ("--queue", "--cue"):
                    settings = settings.with_updates(queue=take_value(name, inline) or settings.queue)
                    continue
                if name in ("--cores", "--nproc"):
                    settings = settings.with_updates(cores=int(take_value(name, inline)))
                    continue
                if name in ("--memory", "--mem"):
                    value = UnitParser.parse_to_mb(take_value(name, inline), settings.memory_mb)
                    settings = settings.with_updates(memory_mb=value or settings.memory_mb)
                    continue
                if name == "--walltime":
                    settings = settings.with_updates(walltime=take_value(name, inline) or settings.walltime)
                    continue
                if name in ("--gaussian-version", "--gauss"):
                    settings = settings.with_updates(gaussian_version=take_value(name, inline) or None)
                    continue
                if name == "--maxdisk":
                    maxdisk = UnitParser.parse_to_mb(take_value(name, inline), settings.maxdisk_mb)
                    settings = settings.with_updates(maxdisk_mb=maxdisk)
                    continue
                if name in ("--preset", "--presets"):
                    preset_value = take_value(name, inline)
                    settings = self._apply_preset(preset_value, settings)
                    continue

                fail(f"Unknown option {name}")

            else:
                # short options, combine like bash getopts did
                name = arg
                option = name[1]
                remainder = name[2:]
                inline = remainder if remainder else None

                if option == "h":
                    print_usage()
                    sys.exit(0)
                if option == "s":
                    settings = settings.with_updates(quiet=True)
                    i += 1
                    continue
                if option == "i":
                    settings = settings.with_updates(quiet=False, show_summary=True)
                    i += 1
                    continue
                if option == "r":
                    settings = settings.with_updates(dry_run=True, show_summary=True)
                    i += 1
                    continue
                if option == "n":
                    settings = settings.with_updates(correction_enabled=False)
                    i += 1
                    continue
                if option == "f":
                    settings = settings.with_updates(force_priority=True)
                    i += 1
                    continue
                if option == "l":
                    selector = take_value("-l", inline)
                    self.logger.show(selector)
                    sys.exit(0)
                if option == "q":
                    settings = settings.with_updates(queue=take_value("-q", inline) or settings.queue)
                    continue
                if option == "c":
                    settings = settings.with_updates(cores=int(take_value("-c", inline)))
                    continue
                if option == "m":
                    value = UnitParser.parse_to_mb(take_value("-m", inline), settings.memory_mb)
                    settings = settings.with_updates(memory_mb=value or settings.memory_mb)
                    continue
                if option == "w":
                    settings = settings.with_updates(walltime=take_value("-w", inline) or settings.walltime)
                    continue
                if option == "g":
                    settings = settings.with_updates(gaussian_version=take_value("-g", inline) or None)
                    continue
                if option == "d":
                    maxdisk = UnitParser.parse_to_mb(take_value("-d", inline), settings.maxdisk_mb)
                    settings = settings.with_updates(maxdisk_mb=maxdisk)
                    continue
                if option == "p":
                    preset_value = take_value("-p", inline)
                    settings = self._apply_preset(preset_value, settings)
                    continue

                fail(f"Unknown option -{option}")

            i += 1

        return CLIResult(files=files, settings=settings)

    def _apply_preset(self, value: str, settings: SubmitSettings) -> SubmitSettings:
        lowered = value.lower()
        if lowered == "show":
            self.preset_manager.show_presets()
            sys.exit(0)
        if lowered == "set":
            self.preset_manager.open_editor()
            sys.exit(0)
        try:
            preset_number = int(value)
        except ValueError:
            print(f"Invalid preset identifier: {value}", file=sys.stderr)
            self.preset_manager.show_presets()
            sys.exit(1)
        preset = self.preset_manager.get_preset(preset_number)
        return settings.update_from_preset(preset_number, preset)


# --------------------------------------------------------------------------------------
# Job orchestration
# --------------------------------------------------------------------------------------


class GaussianJobManager:
    def __init__(
        self,
        paths: Paths,
        script_manager: PBSScriptManager,
        corrector: GaussianInputCorrector,
        scheduler: Scheduler,
        logger: JobLogger,
    ) -> None:
        self.paths = paths
        self.script_manager = script_manager
        self.corrector = corrector
        self.scheduler = scheduler
        self.logger = logger

    def prepare_environment(self, settings: SubmitSettings) -> None:
        self.script_manager.update(settings)

    def process_jobs(self, files: Sequence[str], settings: SubmitSettings) -> None:
        if not files:
            print_usage()
            sys.exit(0)

        self.prepare_environment(settings)

        for raw in files:
            path = self._resolve_input_file(raw)
            self._validate_input_file(path)
            self.corrector.correct(path, settings)

            job_name = path.stem[:15]
            input_stem = path.stem
            command = self._build_command(settings, job_name, input_stem)

            if settings.quiet and (settings.show_summary or settings.dry_run):
                self._print_quiet_summary(path, settings, command)

            if not self._confirm_submission(path, settings, command):
                print(f"{YELLOW}\n Work aborted \n{NC}")
                continue

            if settings.dry_run:
                print("Dry-run: qsub command not executed.")
                continue

            result = self.scheduler.submit(command)
            if result.output:
                print(result.output)
            if not result.succeeded:
                print(f"{YELLOW}\n Submission failed \n{NC}")
                continue

            log_line = self.logger.log_line(result.output, path.stem)
            self.logger.append(log_line)
            print(f"{YELLOW}\n {datetime.utcnow():%H:%M} - Work sent \n{NC}")

    def _build_command(self, settings: SubmitSettings, job_name: str, input_stem: str) -> List[str]:
        command = ["qsub"]
        if settings.force_priority:
            command.extend(["-p", "100"])
        command.extend(["-N", job_name, "-v", f"in={input_stem}", str(self.paths.script_file)])
        return command

    def _confirm_submission(self, path: Path, settings: SubmitSettings, command: Sequence[str]) -> bool:
        if settings.quiet:
            return True

        print(f"{YELLOW}Job overview for {path.name}{NC}")
        print(f"Input file : {path}")
        if settings.preset_loaded is not None:
            print(f"Preset loaded: {settings.preset_loaded}")
        self._interactive_preview(path)
        if settings.whitestripes:
            print(f"{YELLOW}{settings.whitestripes}{NC}")
        print(f"Command    : {' '.join(command)}")
        print(settings.summary())
        if settings.dry_run:
            print("Dry-run mode: submission will not be sent.")
        response = input(
            f"{RED}------------------------------Are you sure? [y/N]-------------------------------{NC}\n "
        )
        return response.strip().lower() in {"y", "yes"}

    def _print_quiet_summary(self, path: Path, settings: SubmitSettings, command: Sequence[str]) -> None:
        print(f"{YELLOW}Job overview for {path.name}{NC}")
        print(f"Input file : {path}")
        print(settings.summary())
        if settings.preset_loaded is not None:
            print(f"Preset loaded: {settings.preset_loaded}")
        if settings.whitestripes:
            print(f"{YELLOW}{settings.whitestripes}{NC}")
        mode = "Dry-run (no submission)" if settings.dry_run else "Queued submission"
        print(f"Mode       : {mode}")
        print(f"Command    : {' '.join(command)}")

    @staticmethod
    def _interactive_preview(path: Path) -> None:
        print(f"{RED}--------------------------------------------------------------------------------{NC}\n")
        try:
            print(path.read_text())
        except UnicodeDecodeError:
            print("(Binary input file – preview skipped)")
        print(f"\n{RED}--------------------------------------------------------------------------------{NC}\n")

    @staticmethod
    def _resolve_input_file(raw: str) -> Path:
        candidate = Path(raw)
        if candidate.exists():
            return candidate
        if candidate.suffix != ".com":
            alternative = candidate.with_suffix(".com")
            if alternative.exists():
                return alternative
        return candidate

    @staticmethod
    def _validate_input_file(path: Path) -> None:
        if not path.exists():
            print(f'"{path}" does not exists.', file=sys.stderr)
            sys.exit(1)
        if path.suffix.lower() != ".com":
            print(f'"{path}" is not a com file.', file=sys.stderr)
            sys.exit(1)


# --------------------------------------------------------------------------------------
# Default file templates
# --------------------------------------------------------------------------------------


DEFAULT_SCRIPT_TEMPLATE = textwrap.dedent(
    """#!/bin/sh

# submit jobs to the que with this script using the following command:
# rng4 is this script
# jobname is a name you will see in the qstat command
# name is the actual file minus .com etc it is passed into this script as ${in%.com}
#
# qsub rng -N jobname -v in=name

# batch processing commands
#PBS -l walltime=119:59:00
#PBS -lselect=1:ncpus=12:mem=48000MB:tmpspace=400gb
#PBS -j oe
#PBS -q pqph
#PBS -m ae

# load modules
#
module load gaussian/g09-d01

# check for a checkpoint file
#
# variable PBS_O_WORKDIR=directory from which the job was submited.
   test -r $PBS_O_WORKDIR/${in%.com}.chk
   if [ $? -eq 0 ]
   then
     echo "located $PBS_O_WORKDIR/${in%.com}.chk"
     cp $PBS_O_WORKDIR/${in%.com}.chk $TMPDIR/.
   else
     echo "no checkpoint file $PBS_O_WORKDIR/${in%.com}.chk"
   fi
#
# run gaussian
#
  g09 $PBS_O_WORKDIR/${in}
  cp $TMPDIR/${in%.com}.chk /$PBS_O_WORKDIR/.
  cp $TMPDIR/${in%.com}.wfx /$PBS_O_WORKDIR/.
#  cp *.chk /$PBS_O_WORKDIR/pbs_${in%.com}.chk
#  test -r $TMPDIR/fort.7
#  if [ $? -eq 0 ]
#  then
#    cp $TMPDIR/fort.7 /$PBS_O_WORKDIR/${in%.com}.mos
#  fi
# exit
"""
)


DEFAULT_PRESET_TEMPLATE = textwrap.dedent(
    """##     Here is where to list the preset for gaussian calculations
##     Each line is a preset and it is written in this way :
##             [CUE];[CORES];[MEMORY];[WALLTIME];[GAUSSIAN VERSION];[MAXDISK]
##     e.g      pqph;8;14400MB;119:59:00;d01;800GB
##
##
##-----------------------------------------------------------------------------
##
##     presets starts from next line
pqph;12;48000MB;119:59:00;d01;400GB
"""
)


# --------------------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------------------


def build_app() -> Tuple[GaussianJobCLI, GaussianJobManager, SubmitSettings]:
    paths = Paths()
    paths.ensure_support_files()

    preset_manager = PresetManager(paths)
    logger = JobLogger(paths)
    cli = GaussianJobCLI(preset_manager, logger)

    script_manager = PBSScriptManager(paths)
    corrector = GaussianInputCorrector()
    scheduler = PBSScheduler()
    manager = GaussianJobManager(paths, script_manager, corrector, scheduler, logger)

    settings = SubmitSettings()
    return cli, manager, settings


def main(argv: Sequence[str]) -> None:
    cli, manager, settings = build_app()
    result = cli.parse(argv, settings)
    manager.process_jobs(result.files, result.settings)


def entry_point() -> None:
    try:
        main(sys.argv[1:])
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    entry_point()
