# HPC-tracking_manager
A BASH script aimed at sending Gaussian works to HPC, recording the works sent to the HPC, and track their execution. Auto input files correction and work profile pre-setting included.
The script had been translated into python later on by my former Master supervisor Patricia Hunt. I am sure she has done a great job at translating it to python. Here you may find the python revamp of my code: https://sagacioushours.org.uk/wiki/index.php?title=Mod:Hunt_Research_Group/new_gf_script

---

# 🧠 `gf` — Speed Up Your HPC Job Queuing

This is a tiny but powerful helper script to **speed up job submission** to your HPC queue system—especially for Gaussian jobs. It also **auto-corrects** your `.com` input files on the fly, syncing memory, core count, checkpoint filenames, and more based on your terminal input.

Big thanks to Claire for the original script this is based on!

---

## 🚀 Installation

In your HPC terminal:

```bash
vi ~/bin/gf
```

Paste the contents of the script (see below) into the file. Then save and make it executable:

```bash
chmod +x ~/bin/gf
```

You're all set! Use `gf` just like any regular terminal command.

---

## 🧰 Features

- Fast job queuing with customizable settings
- Auto-correction of:
  - `%mem=...`
  - `%nprocshared=...`
  - `%chk=...`
  - `maxdisk=...` (if present)
- Preset system for different job types
- Easy log access to previously sent jobs
- Silent (auto-submit) or interactive modes
- Built-in editor for preset configuration

---

## 📦 Usage

```bash
gf your_job_file.com [options]
```

If `your_job_file.com` is not specified, the script shows help.

---

## 🛠 Options

| Option         | Description                                                                 |
|----------------|-----------------------------------------------------------------------------|
| `-q [cue]`     | Set the queue for the job (default: `pqph`)                                |
| `-c [cores]`   | Set number of cores (default: 12)                                           |
| `-m [memory]`  | Set memory in MB or GB (e.g. `16000MB` or `16GB`)                          |
| `-w [time]`    | Set walltime (e.g. `72:00:00`)                                              |
| `-g [version]` | Set Gaussian version (e.g. `d01`)                                           |
| `-s`           | Silent mode – skips preview, submits directly                              |
| `-n`           | Disable auto-correction of input file                                       |
| `-d [disk]`    | Set max disk space in MB/GB                                                 |
| `-p [preset]`  | Load preset by index, or use `show`/`set` to manage them                    |
| `-l [id/all]`  | View logs – either all, or by job ID                                        |
| `-f`           | Force priority submission (`qsub -p 100`)                                  |
| `-h`           | Show help message                                                           |

---

## 🎛 Presets

You can define presets in `~/bin/.presets` for fast loading via `-p`:

```txt
pqph;8;16000MB;72:00:00;d01;400GB
```

To view available presets:

```bash
gf -p show
```

To edit presets:

```bash
gf -p set
```

---

## 📄 Input File Correction

If enabled (default), `gf` will:

- Set `%chk=` to match the input filename
- Update `%mem=` to a safe 75% of total memory
- Set `%nprocshared=` to match `-c` option
- Adjust `maxdisk=...` if found in the file

Disable this with `-n`.

---

## 📜 Logging

Every job submission is logged in:

- `~/.wlog` – all jobs
- `~/.wulog` – alternate log format

Check logs with:

```bash
gf -l all        # show all logs
gf -l 7197851    # show a specific job by ID
```

---

## 📌 Example

```bash
gf mycalc.com -c 8 -m 16000MB -q pqph -w 72:00:00 -g d01
```

Will:
- Correct your input file with 8 cores and 12GB mem
- Submit to the `pqph` queue
- Use Gaussian `g09-d01`
- Log everything automatically

---

## ✅ Pro Tip

Short command name = faster workflow:

```bash
gf job.com -s
```

---

## ❤️ Credits

Original batch script adapted from Claire — thanks!

---
