import os
import sys
import argparse
import json
import subprocess
from pathlib import Path
from datetime import datetime
from abc import ABC, abstractmethod

class HPCJob(ABC):
    def __init__(self, input_file, args, presets):
        self.input_file = Path(input_file)
        self.args = args
        self.presets = presets or {}
        self.settings = self.merge_settings()
        self.job_name = self.input_file.stem
        self.script_path = self.input_file.with_suffix('.pbs')

    def merge_settings(self):
        settings = vars(self.args).copy()
        settings.update(self.presets.get(self.args.preset, {}))
        return settings

    @abstractmethod
    def ensure_input(self):
        pass

    @abstractmethod
    def generate_job_script(self):
        pass

    @abstractmethod
    def submit_command(self):
        pass

    def preview(self):
        print(f"\n--- Job Script Preview for {self.input_file.name} ---\n")
        print(self.script_path.read_text())

    def confirm_and_submit(self):
        if self.args.preview:
            self.preview()
        if not self.args.no_interactive:
            confirm = input("Submit this job? (y/n): ")
            if confirm.lower() != 'y':
                return
        subprocess.run(self.submit_command())

class GaussianJob(HPCJob):
    def ensure_input(self):
        with open(self.input_file, 'r') as f:
            lines = f.readlines()

        directives = [line for line in lines if line.strip().startswith('%')]
        if not any('%mem' in d for d in directives):
            lines.insert(0, f"%mem={self.settings['mem'] or '2GB'}\n")
        if not any('%nprocshared' in d for d in directives):
            lines.insert(1, f"%nprocshared={self.settings['nproc'] or 1}\n")

        with open(self.input_file, 'w') as f:
            f.writelines(lines)

    def generate_job_script(self):
        mem = self.settings['mem'] or '2GB'
        nproc = self.settings['nproc'] or 1
        walltime = self.settings['walltime'] or '1:00:00'
        queue = self.settings['queue'] or 'default'
        module = self.settings['module'] or 'gaussian/g16'

        script = f"""#!/bin/bash
#PBS -N {self.job_name}
#PBS -l nodes=1:ppn={nproc}
#PBS -l walltime={walltime}
#PBS -q {queue}
#PBS -o {self.job_name}.out
#PBS -e {self.job_name}.err

module load {module}

cd $PBS_O_WORKDIR

export GAUSS_SCRDIR=/scratch/$USER/{self.job_name}_$PBS_JOBID
mkdir -p $GAUSS_SCRDIR

g16 < {self.input_file.name} > {self.job_name}.log

rm -rf $GAUSS_SCRDIR
"""
        self.script_path.write_text(script)

    def submit_command(self):
        return ['qsub', str(self.script_path)]

class ORCAJob(HPCJob):
    def ensure_input(self):
        # ORCA input modification can be added here if necessary
        pass

    def generate_job_script(self):
        mem = self.settings['mem'] or '2GB'
        nproc = self.settings['nproc'] or 1
        walltime = self.settings['walltime'] or '1:00:00'
        queue = self.settings['queue'] or 'default'
        module = self.settings['module'] or 'orca/5.0.1'

        script = f"""#!/bin/bash
#PBS -N {self.job_name}
#PBS -l nodes=1:ppn={nproc}
#PBS -l walltime={walltime}
#PBS -q {queue}
#PBS -o {self.job_name}.out
#PBS -e {self.job_name}.err

module load {module}

cd $PBS_O_WORKDIR

orca {self.input_file.name} > {self.job_name}.log
"""
        self.script_path.write_text(script)

    def submit_command(self):
        return ['qsub', str(self.script_path)]

class HPCBatchSubmitter:
    def __init__(self):
        self.args = self.parse_args()
        self.presets = self.load_presets()
        self.files = self.collect_input_files()

    def parse_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('files', nargs='*', help="Input files")
        parser.add_argument('--mem', help='Memory allocation')
        parser.add_argument('--nproc', type=int, help='Number of processors')
        parser.add_argument('--walltime', help='Walltime for the job')
        parser.add_argument('--queue', help='Queue name')
        parser.add_argument('--module', help='Module to load')
        parser.add_argument('--preset', default=None, help='Preset name')
        parser.add_argument('--preview', action='store_true', help='Preview job scripts without submitting')
        parser.add_argument('--no-interactive', action='store_true', help='Disable interactive confirmation')
        parser.add_argument('--software', choices=['gaussian', 'orca'], default='gaussian', help='Software package to use')
        return parser.parse_args()

    def load_presets(self):
        preset_path = Path.home() / f".{self.args.software}_presets.json"
        if preset_path.exists():
            return json.loads(preset_path.read_text())
        return {}

    def collect_input_files(self):
        extension = {
            'gaussian': '.com',
            'orca': '.inp'
        }.get(self.args.software, '.com')
        if self.args.files:
            return [f for f in self.args.files if f.endswith(extension)]
        else:
            return list(Path('.').glob(f'*{extension}'))

    def create_job(self, input_file):
        if self.args.software == 'gaussian':
            return GaussianJob(input_file, self.args, self.presets)
        elif self.args.software == 'orca':
            return ORCAJob(input_file, self.args, self.presets)
        else:
            raise ValueError("Unsupported software specified.")

    def run(self):
        for input_file in self.files:
            job = self.create_job(input_file)
            job.ensure_input()
            job.generate_job_script()
            job.confirm_and_submit()

if __name__ == '__main__':
    submitter = HPCBatchSubmitter()
    submitter.run()
