#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import json
import logging
import os
import re
import shutil
import tempfile

import ruamel.yaml

TAG_RE = re.compile(r"<[^>]+>")

logging.basicConfig(level=logging.INFO)


def _remove_tags(content: str) -> str:
    """
    Remove HTML tags from the content string
    """
    return TAG_RE.sub("", content)


def _read_frontmatter_as_yaml(content: list[AnyStr]) -> Dict[str, Any]:
    """
    Read the FrontMatter in YAML format. (https://frontmatter.codes/docs/markdown)
    """
    extract = ""
    for i in range(1, len(content)):
        if content[i].rstrip() == "---":
            break
        extract += content[i]

    logging.debug("extract : {}".format(extract))

    yaml = ruamel.yaml.YAML(typ="safe")
    return yaml.load(extract)


def _extract_from_frontmatter_variables(
    frontmatter: Dict[str, Any], frontmatter_from_file: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Read the Frontmatter values to extract variables
    """

    logging.debug("frontmatter_from_file: %s", frontmatter_from_file)

    if "activity" in frontmatter_from_file:
        frontmatter["activity"] = frontmatter_from_file["activity"]

    if "activity_tp" in frontmatter_from_file:
        frontmatter["activity_tp"] = frontmatter_from_file["activity_tp"]

    if "tool" in frontmatter_from_file:
        frontmatter["tool"] = frontmatter_from_file["tool"]

    if "objective" in frontmatter_from_file:
        frontmatter["objective"] = frontmatter_from_file["objective"]

    if "duration" in frontmatter_from_file:
        frontmatter["duration"] = frontmatter_from_file["duration"]

    logging.debug("frontmatter: %s", frontmatter)


def _extract_chapters_from_md_file(filename: str, toc: Dict[str, Any]):
    """
    Read a Markdown file representing a Chapter.

    Fist check if there is a Frontmatter to override default values.

    Then parse each line to find titles (level 1 & 2) and TP to complete `toc`
    """

    with open(filename, "r", encoding="utf-8") as chapter:
        content = chapter.readlines()

        # default values
        frontmatter = {
            "activity": "Slides et Explication",
            "activity_tp": "TP et Démo",
            "tool": "Strigo",
            "objective": "To be defined",
            "duration": "~0",
        }

        if content[0].rstrip() == "---":
            _extract_from_frontmatter_variables(
                frontmatter, _read_frontmatter_as_yaml(content)
            )

        nb_sub_chapter = 0
        for i in range(0, len(content)):
            current_line = content[i]
            if current_line.startswith("#"):
                nb_sub_chapter = nb_sub_chapter + 1

        for i in range(0, len(content)):
            current_line = content[i]
            if current_line.startswith("# "):
                # Compter le nombre de page du chapitre
                toc.append(
                    {
                        "id": len(toc),
                        "level": 1,
                        "title": _remove_tags(current_line.rstrip()),
                        "activity": frontmatter["activity"],
                        "tool": frontmatter["tool"],
                        "objective": frontmatter["objective"],
                        "duration": frontmatter["duration"],
                        "nb_sub_chapter": nb_sub_chapter,
                    }
                )
            if current_line.startswith("## "):
                toc.append(
                    {
                        "id": len(toc),
                        "level": 2,
                        "title": _remove_tags(current_line.rstrip()),
                        "activity": frontmatter["activity"],
                        "tool": frontmatter["tool"],
                        "objective": "",
                        "duration": "",
                    }
                )
            # <!-- .slide: class="page-tp" data-label="TP 2 : Concepts Keycloak" -->
            if current_line.startswith('<!-- .slide: class="page-tp" '):
                data_label = _remove_tags(current_line[41:].partition('"')[0])
                toc.append(
                    {
                        "id": len(toc),
                        "level": 2,
                        "title": data_label,
                        "activity": frontmatter["activity_tp"],
                        "tool": frontmatter["tool"],
                        "objective": "",
                        "duration": "",
                    }
                )


def _read_slides_list_to_extract_chapters(training_name: str, slides_path: str) -> list:
    """
    Read the slides.json file to parse each md file to extract toc from trusted datas.
    """
    toc = []

    with open(slides_path + "/slides.json", "r", encoding="utf-8") as file:
        data = json.load(file)
        for file in data:
            _extract_chapters_from_md_file(slides_path + "/" + file, toc)

    logging.debug("toc: [\n{}\n]".format(",\n".join(map(str, toc))))

    return toc


def _merge_with_previous_version(csv_filename: str, toc: list):
    """
    Find by title in previous CSV file, the values to use instead of default.
    """
    logging.info("Merge with previous extract " + csv_filename + " file")

    prev_csv_filename = "tmp/tmp.csv"
    logging.info("Moving from " + csv_filename + " to " + prev_csv_filename)
    shutil.move(csv_filename, prev_csv_filename)

    prev_csv_indexed = {}

    # index prev_csv_filename, by title
    with open(prev_csv_filename, newline="") as existing_csvfile:
        existing_csv_content = csv.reader(existing_csvfile, delimiter=";")

        for row in existing_csv_content:
            prev_csv_indexed[row[2]] = row

    for entry in toc:
        logging.debug("Looking for title : %s", entry["title"])
        if entry["title"] in prev_csv_indexed:
            prev_csv_row = prev_csv_indexed[entry["title"]]

            # activity
            if (
                entry["title"].startswith("#")
                and entry["activity"] == "Slides et Explication"
                and prev_csv_row[3] != "Slides et Explication"
            ):
                entry["activity"] = prev_csv_row[3]
            # activity_tp
            if (
                not entry["title"].startswith("#")
                and entry["activity"] == "TP et Démo"
                and prev_csv_row[3] != "TP et Démo"
            ):
                entry["activity"] = prev_csv_row[3]
            # tool
            if entry["tool"] == "Strigo" and prev_csv_row[4] != "Strigo":
                entry["tool"] = prev_csv_row[4]
            # objective
            if (
                entry["objective"] == "To be defined" or entry["objective"] == ""
            ) and prev_csv_row[5] != "To be defined":
                entry["objective"] = prev_csv_row[5]
            # duration
            if str(entry["duration"]).startswith("~") and not str(
                prev_csv_row[6]
            ).startswith("~"):
                entry["duration"] = prev_csv_row[6]


def _compute_estimated_duration(toc, training_duration):
    """
    Set an estimated duration for chapters based on (nb_sub_chapter) * (training_duration in minutes) / (total_nb_chapter)
    """
    logging.debug(" training_duration %s", training_duration)

    total_nb_chapter = 0
    for entry in toc:
        if entry["level"] == 1:
            total_nb_chapter = total_nb_chapter + int(entry["nb_sub_chapter"])
    logging.debug("total_nb_chapter %s", total_nb_chapter)

    avg_time_by_slide = training_duration * 7 * 60 / total_nb_chapter
    logging.debug(" avg_time_by_slide %s", avg_time_by_slide)

    for entry in toc:
        if entry["level"] == 1 and str(entry["duration"]).startswith("~"):
            val = round(entry["nb_sub_chapter"] * avg_time_by_slide)
            entry["duration"] = "~" + str(val)


def _save_in_csv_format_after_merge_with_prev_version(
    training_path: str, training_name: str, toc: list
):
    """
    Initialisation (aka: first run) is when no CSV file is found for this training name.

    For other runs, move the existing csv file, read it to import values to replace "defaults" ones
    """
    os.makedirs(training_path + "/data", exist_ok=True)

    csv_filename = training_path + "/data/" + training_name + ".csv"
    fields = [
        "id",
        "level",
        "title",
        "activity",
        "tool",
        "objective",
        "duration",
        "nb_sub_chapter",
    ]

    if os.path.isfile(csv_filename):
        _merge_with_previous_version(csv_filename, toc)

    logging.info("Save extract in " + csv_filename + " file")
    with open(csv_filename, "w", newline="") as file:

        writer = csv.DictWriter(file, fieldnames=fields, delimiter=";")

        # write the header
        writer.writeheader()

        # write the data
        writer.writerows(toc)


def _get_training_name(path: str) -> str:
    """
    First line of PLAN.md containt the training name
    """
    firstLine = "Unreadable"
    with open(path + "/PLAN.md", "r") as plan:
        firstLine = plan.readline()

    firstLine = firstLine.replace("#", "").strip().replace(" ", "-").lower()

    logging.info("The rewrite training name is : %s", firstLine)

    return firstLine


def _get_training_duration(path: str) -> int:
    """
    Find 'Durée' in PLAN.m to get the training_duration
    """
    training_duration = 0

    with open(path + "/PLAN.md", "r") as plan:
        lines = plan.readlines()
        for line in lines:
            if line.startswith("Durée:"):
                training_duration = line[6:].strip()

            if line.startswith("Durée :"):
                training_duration = line[7:].strip()

    if training_duration.endswith("j"):
        training_duration = training_duration[:-1]

    return int(training_duration)


def main(argv: Sequence[str] | None = None):
    """Extract plan from slides and MD files"""

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "path",
        help="Path where to find `PLAN.md` and `Slides\slides.json`.",
    )
    args = parser.parse_args(argv)

    training_name = _get_training_name(args.path)
    training_path = args.path

    training_duration = _get_training_duration(training_path)

    if training_duration == 0:
        logging.error(
            "Training duration not found in PLAN.md (looking for exact string : `Durée :`)"
        )
        exit(-1)

    logging.info("Training : %s", training_name)
    logging.info("Path     : %s", training_path)

    toc = _read_slides_list_to_extract_chapters(
        training_name, training_path + "/Slides"
    )

    _compute_estimated_duration(toc, training_duration)

    _save_in_csv_format_after_merge_with_prev_version(training_path, training_name, toc)


if __name__ == "__main__":
    raise SystemExit(main())
