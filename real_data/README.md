# Real event logs used in the paper

This directory documents, but does not redistribute, the three public event
logs used in Section 6.1 ("Evaluating Real Event Logs") of the paper. All
three are standard 4TU.ResearchData releases with their own DOIs and license
terms, so we point to the source and give exact checksums instead of
re-hosting the files.

| Dataset id  | Paper name                         | DOI                                              | Cases   | Variants | Activities |
|-------------|-------------------------------------|---------------------------------------------------|---------|----------|------------|
| `road_fines`| Road Traffic Fine Management Process| 10.4121/uuid:270fd440-1057-4fb9-89a9-b699b47990f5  | 150,370 | 231      | 11         |
| `sepsis`    | Sepsis Cases - Event Log            | 10.4121/uuid:915d2bfb-7e84-49ad-a286-dc35f063a460  | 1,050   | 846      | 16         |
| `bpi_2012`  | BPI Challenge 2012                  | 10.4121/uuid:3926db30-f712-4394-aebc-75976070e91f  | 13,087  | 4,366    | 24         |

Case/variant/activity counts here are computed directly from the logs (see
`dataset_profiles.csv`), not taken from the dataset's own documentation, so
they can be used as a sanity check after download.

## Getting the logs

Run `download_datasets.sh`, or fetch them by hand from the DOIs above. Either
way, verify the checksum before using a file:

```bash
sha256sum -c checksums.sha256
```

Expected layout after download:

```
raw/road_fines/Road_Traffic_Fine_Management_Process.xes.gz
raw/sepsis/Sepsis Cases - Event Log.xes.gz
raw/bpi_2012/RequestForPayment.xes.gz
```

`dataset_manifest.json` is the exact dataset section of the pipeline's
configuration file, with the local machine path stripped out. `core/`
resolves the data root via the `LMP_VEXG_DATA_ROOT` environment variable at
run time, so pointing it at wherever you put `raw/` above is enough to
reproduce the profiling and discovery steps, e.g.:

```bash
export LMP_VEXG_DATA_ROOT="$(pwd)/real_data"
```

## A note on the BPI 2012 file name

The BPI 2012 archive is distributed by 4TU under a folder/file name that
still carries its original submission label,
`bpi_challenge_2020_request_for_payment/RequestForPayment.xes.gz`. This is a
naming artifact from how the file was archived, not a different dataset: the
file's own `DATA.xml` and internal XES metadata identify it as BPI Challenge
2012 (DOI above), and its event/case counts (13,087 cases, 262,200 events)
match the published BPI 2012 statistics exactly. We keep the original file
name in `checksums.sha256` for traceability but use `bpi_2012` as the
experiment id everywhere else, including in the paper.

## Licensing

All three logs are released for research use by their original custodians
(Eindhoven University of Technology / 4TU.ResearchData). Check the DOI
landing pages for the exact license and citation requirements before
redistributing derived data.
