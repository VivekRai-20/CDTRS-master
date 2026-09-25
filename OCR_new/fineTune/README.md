# Fine-tuning the OCR on your own handwriting

This folder teaches CDTRS to read **your** handwriting better, using scans
(images or PDFs) that you label yourself. Everything runs on your own PC, with no
internet connection and only the packages that are already installed from `imp.txt`.

You can improve three things. You only need the first one.

| What | Why | Command |
|---|---|---|
| **Handwriting reading** (TrOCR model) | Reads handwritten lines (notes, instructions, forms) that PaddleOCR gets wrong | `train.py --task handwriting` |
| Printed / handwritten detection | Decides which lines go to the handwriting model | `train.py --task text_type` |
| Document categories (optional) | Uses your own categories in OCR results | `train.py --task classification` |

PaddleOCR itself (the printed-text reader) is not retrained. Its training tools are
not part of the installed `paddleocr` package, and it already reads print well.

---

## How it works

```
page ──► PaddleOCR finds every text line and reads it
             │
             ├─► printed / handwritten detector labels each line
             │
             └─► HANDWRITTEN lines (and unsure lines with low confidence) are read
                 again by the handwriting model; its reading replaces PaddleOCR's
                 when it is more confident
```

The handwriting model is **Microsoft TrOCR** (`trocr-small-handwritten`). It is
trained on English handwriting, but not on yours. Fine-tuning shows it a few hundred
or thousand of your own lines with the correct text, so it adapts to your writers,
pens, forms and vocabulary.

---

## Before you start (once)

Open a Command Prompt in the `OCR_new` folder. In File Explorer, open
`C:\CDTRS-main\OCR_new`, click the address bar, type `cmd` and press Enter.

1. Check that the PaddleOCR models are in place:

   ```
   python setup_models.py --check
   ```

2. Download the handwriting base model. This is the only step that needs the
   internet. It downloads about 250 MB into `models\handwriting\trocr-small-handwritten\`
   and makes that model active:

   ```
   python fineTune/download_base_model.py
   ```

   If this PC has no internet, run the same command on another PC and copy the
   `models\handwriting\` folder across.

> If `python` is not recognised, use `py -3.12` instead. You can also skip the
> Command Prompt: the numbered `.bat` files in this folder (`1_prepare_dataset.bat`,
> `2_label_lines.bat`, …) do each step when you double-click them. They find
> Python 3.12 by themselves.

---

## The folders

```
OCR_new/fineTune/
├── datasets/
│   ├── raw/              ← STEP 1: put your scans / photos / PDFs here (sub-folders are fine)
│   ├── lines/            ← one image per text line (made for you)
│   ├── labels.csv        ← one row per line: the correct text and its type (you fill it in)
│   └── classification/   ← optional: documents sorted into <CATEGORY>/ folders
├── configs/              ← training settings (handwriting.yaml, text_type.yaml, classification.yaml)
├── checkpoints/          ← training runs and logs (safe to delete)
├── evaluation/reports/   ← saved evaluation results
├── prepare_dataset.py    ← STEP 1
├── label_tool.py         ← STEP 2
├── training/train.py     ← STEP 3
├── evaluation/evaluate.py← STEP 4
└── set_active_model.py   ← choose / roll back the model in use
```

Trained models are saved outside this folder, where the OCR looks for them:

```
OCR_new/models/handwriting/
├── trocr-small-handwritten/   the downloaded base model
├── v1/, v2/, …                your fine-tuned versions (each has model_meta.json with its scores)
└── active.txt                 the name of the one CDTRS uses
OCR_new/models/classifiers/text_type/classifier.pkl   your printed/handwritten detector
OCR_new/models/classifiers/document/                  your document classifier
```

Git does not track the datasets, labels or trained models (see `.gitignore`).
Your scans may be confidential, and the models are large. **Back up
`fineTune\datasets\` yourself.** Your labelling work is stored there.

---

## Step 1: Collect and prepare your scans

Copy your handwriting images or PDFs into `fineTune\datasets\raw\`. You can use any
number of files and sub-folders, for example `raw\notesheets_2025\`,
`raw\forms\`. Supported types: PNG, JPG, TIFF, BMP, WEBP and PDF (every page is used).

For good results:

- Scan at **300 DPI**, straight and flat. Phone photos work if they are sharp
  and evenly lit.
- Include the **variety you really get**: different writers, pens, paper, forms, and
  printed pages with handwritten notes on them.
- More labelled lines give better results:

  | Labelled handwritten lines | What to expect |
  |---|---|
  | 100–300 | A first, noticeable improvement on those writers |
  | 1,000–3,000 | Clearly better on your documents |
  | 5,000+ | Best results, including new writers |

Then run **(1_prepare_dataset.bat)**:

```
python fineTune/prepare_dataset.py
```

For every page, PaddleOCR finds the text lines and saves each one as an image
in `datasets\lines\`. Each line also gets a row in `datasets\labels.csv` with
PaddleOCR's reading and a printed/handwritten guess. A page takes about 20–40 seconds.

Running it again later **only adds new files**. Labels you already made are kept,
so you can add scans at any time.

Other options:

| Command | What it does |
|---|---|
| `python fineTune/prepare_dataset.py --stats` | Shows how many lines are labelled |
| `python fineTune/prepare_dataset.py --lines` | Treats each file in `raw\` as a single line already |
| `python fineTune/prepare_dataset.py --min-height 20` | Ignores tiny boxes (the default is 12 px) |

With `--lines`, each image in `raw\` is one text line. If a `.txt` file with the
same name exists (for example `line001.png` and `line001.txt`), its text is taken
as the correct label. Add `--type PRINTED` if those lines are printed.

---

## Step 2: Label the lines

Run **(2_label_lines.bat)**:

```
python fineTune/label_tool.py
```

For every line image:

1. **Type the text exactly as it is written.** The box starts with PaddleOCR's
   reading, so often you only fix a few characters.
2. Choose **Handwritten** or **Printed**.
3. Press **Enter** to save and go to the next line.

| Key | Action |
|---|---|
| Enter | Save and go to the next line |
| Ctrl+H / Ctrl+P | Mark Handwritten / Printed |
| Ctrl+K | **Skip**: not a usable text line (stamp, signature, drawing, cut-off or unreadable line) |
| Page Down / Page Up | Next / previous line without saving |
| Ctrl+G | Put PaddleOCR's reading back into the box |

Rules for good labels:

- Type what is **written**, including the writer's spelling mistakes,
  abbreviations, capital letters and punctuation. Do not correct or expand anything.
- Keep the words in order, separated by single spaces.
- If you cannot read a word with certainty, **Skip** the whole line. Guessed labels
  teach the model the wrong thing.
- If a line has printed and handwritten parts (for example `Name: Ramesh Kumar`), type
  all of it. Mark it **Handwritten** if the handwritten part matters.
- Label the printed lines too, at least a few hundred. They train the printed/handwritten
  detector.

Every save goes into `labels.csv` straight away, so you can stop and continue at
any time. Use the **Show** list to review what you did (Handwritten, Printed,
Skipped, Test split).

**Using Excel instead:** you can also fill in `labels.csv` in Excel. Put the correct
text in the `text` column and `HANDWRITTEN`, `PRINTED` or `SKIP` in the `type`
column. Save it as *CSV UTF-8*, then **close Excel** before you run any other step.
The tools cannot write the file while Excel has it open.

### The split column: train, val and test

Each line is put in one group automatically, and it always stays there:

- **train** (about 80%): the model learns from these.
- **val** (about 10%): checked after every training pass to keep the best version.
- **test** (about 10%): **never** used for training. Every model is scored on these,
  so the scores are honest.

Do not change the split of lines after you have started training.

---

## Step 3: Train the handwriting model

Run **(3_train_handwriting.bat)**:

```
python fineTune/training/train.py --task handwriting
```

What happens:

1. Starts from the **active** model (at first the downloaded base model; later your
   latest version, so each round builds on the previous one).
2. Trains on your labelled HANDWRITTEN `train` lines. It uses small random changes
   (tilt, slant, blur, pen thickness) so it does not just memorise your scans.
3. After every pass (*epoch*), reads the `val` lines and keeps the best version. It
   stops early when this stops improving.
4. Scores the new model, the previous model and PaddleOCR on the **test** lines.
5. Saves the new model as the next version, `models\handwriting\v1`, `v2`, …
6. **Makes it active only if it reads the test lines better** than the previous model
   and PaddleOCR. Otherwise it is kept but not used.

Typical output:

```
[10:02:11] Lines: train 812, val 97, test 104 (handwritten)
[10:02:40] Before training: validation CER 0.214  WER 0.482
[10:10:05] Epoch 1/15: loss 1.873  val CER 0.151  WER 0.371  (445s)
...
[11:31:52] TEST lines (104):  new model CER 0.082  |  previous (trocr-small-handwritten) 0.209  |  PaddleOCR 0.187
[11:31:55] Saved: ...\models\handwriting\v1
[11:31:55] ACTIVE handwriting model is now v1.  Restart the CDTRS backend to use it.
```

**CER** is the *character error rate*: 0.08 means 8 characters in 100 are wrong.
**WER** is the same for whole words. Lower is better.

**Time:** on an ordinary PC without a graphics card, expect about half a second per
line per pass. For example, 1,000 lines × 15 passes takes about 2 hours. (The installed
PyTorch is the CPU version, so a graphics card is not used.) The `.bat` file also writes
everything to `fineTune\checkpoints\train_handwriting.log`.

Useful options (you can also set these in `configs\handwriting.yaml`):

| Option | Effect |
|---|---|
| `--epochs 20` | More passes (the default is 15; training stops early anyway) |
| `--batch-size 4` | Uses less memory (the default is 8; try 4 or 2 if you run out of memory) |
| `--learning-rate 1e-5` | Learns more gently (use it if the val CER jumps up and down) |
| `--base-model trocr-small-handwritten` | Starts again from the base model |
| `--activate` | Always makes the new model active |
| `--no-activate` | Never makes it active; the model is only saved |

For example: `python fineTune/training/train.py --task handwriting --epochs 20 --batch-size 4`

The model needs at least 20 labelled handwritten `train` lines to start (`min_train_lines`).
It can only decide whether the new model is better when some `test` lines are labelled.

---

## Step 4: Check the results

Run **(4_evaluate.bat)**:

```
python fineTune/evaluation/evaluate.py --show 10
```

This compares PaddleOCR with every installed handwriting model on the same
test lines, and lists the 10 lines the active model reads worst:

```
Handwritten lines, split 'test': 104

  Reader                               CER     WER
  -------------------------------- ------- -------
  PaddleOCR                          0.187   0.402
  trocr-small-handwritten            0.209   0.455
  v1                                 0.082   0.214  ACTIVE best
```

Options: `--split val|train|all`, `--models v1 v2`, `--report` (saves the numbers in
`evaluation\reports\`).

The worst lines are often **labelling mistakes**. Fix them in the label tool, using
the *Test split* view.

---

## Step 5: Use the model in CDTRS

**Restart the CDTRS backend.** The OCR loads the active handwriting model when it
starts. New uploads are then read with it.

To see or change which model is in use **(6_choose_model.bat)**:

| Command | What it does |
|---|---|
| `python fineTune/set_active_model.py` | Lists the models with their test scores; `*` marks the active one |
| `python fineTune/set_active_model.py v2` | Uses v2 |
| `python fineTune/set_active_model.py trocr-small-handwritten` | Goes back to the base model |
| `python fineTune/set_active_model.py --off` | Uses no handwriting model (PaddleOCR only) |

Then restart the backend again. Old versions are never deleted automatically. When
you are sure you no longer need one, delete its folder in `models\handwriting\`.

Related settings are in `OCR_new\config\config.yaml` under `handwriting:`:

- `enabled`
- `replace_below_confidence`: lines PaddleOCR is less sure about than this are re-read.
- `min_confidence`: the handwriting reading must be at least this confident.
- `num_beams`
- `device`: keep `cpu`. The installed PyTorch is the CPU build.

---

## Improving it over time

1. Put new scans in `datasets\raw\`.
2. Run `prepare_dataset.py`. Only the new files are added.
3. Label the new lines. The label tool opens on *Not labelled yet*.
4. Run `train.py --task handwriting`. It continues from the active version and
   uses **all** labelled lines, old and new.
5. Run `evaluate.py`, then restart the backend if a new version became active.

Focus your labelling on the kind of pages the OCR still gets wrong. Those lines
help the most.

---

## Printed / handwritten detector (optional)

If printed lines are sent to the handwriting model, or handwritten lines are
missed, train the detector on your labelled lines. You need at least 20 HANDWRITTEN
and 20 PRINTED lines. **(5_train_text_type.bat)**:

```
python fineTune/training/train.py --task text_type
python fineTune/evaluation/evaluate.py --task text_type --split all
```

It is installed in `models\classifiers\text_type\classifier.pkl` only if it scores
at least as well as the built-in detector on the test lines. Add `--activate` to install
it anyway. The previous file is kept as `classifier_<date>.pkl`. To go back to the
built-in detector, delete or rename `classifier.pkl`. Restart the backend after
any change.

## Document categories (optional)

Sort example documents into one folder per category, with at least 5 per category:

```
fineTune\datasets\classification\LEAVE\*.pdf
fineTune\datasets\classification\PURCHASE\*.pdf
fineTune\datasets\classification\CIRCULAR\*.png
```

PDF, images, DOCX and TXT are accepted. Then run:

```
python fineTune/training/train.py --task classification
python fineTune/evaluation/evaluate.py --task classification --folder <folder with new examples>
```

Scans are read by the OCR once and cached next to them as `<name>.ocr.txt`. The
model goes to `models\classifiers\document\`. The OCR uses it instead of the keyword
rules when it is at least 60% sure (`classification.min_model_confidence` in
`config.yaml`). CDTRS department routing still uses the department descriptions and
keywords set in the admin screen. This category is extra information.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No handwriting model to start from` | Run `python fineTune/download_base_model.py` (needs internet once) |
| `Only N labelled training lines` | Label more lines, at least 20 HANDWRITTEN lines in the `train` split |
| `labels.csv is open in another program` | Close Excel |
| Training stops with a memory error | `--batch-size 4` (or 2); close other programs |
| New model "Not activated" | It was not better on the test lines. Label more lines, check the worst lines for label mistakes, or use `--activate` if you are sure |
| val CER goes up and down, or gets worse | `--learning-rate 1e-5`; check the labels |
| The backend still reads the old way | Restart the backend; check `set_active_model.py` shows `*` on the right model |
| `No images or PDFs found` | Files must be in `fineTune\datasets\raw\` (sub-folders are fine) |
| Everything is slow | Normal on CPU. Label in several sessions and train overnight |

## Packages used

Only packages pinned in `imp.txt` / `OCR_new/requirements.txt` are used:

- `torch` and `transformers` for TrOCR training
- `paddleocr` for line detection
- `opencv-python`, `Pillow` and `PyMuPDF` for images and PDFs
- `PySide6` for the label tool
- `scikit-learn` for the classifiers
- `editdistance` for the error rates
- `PyYAML` for the settings files
- `huggingface_hub` for the one-time download
