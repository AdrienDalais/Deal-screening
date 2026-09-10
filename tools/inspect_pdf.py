"""Report the STRUCTURE of a PDF. Never its contents.

    python -m tools.inspect_pdf "/path/to/document.pdf"

Written so that a confidential document can be characterised without any
part of it being disclosed. The output contains page dimensions, counts,
and statistical summaries — no words, no numbers from the document, no
file name unless you pass one that reveals something.

Read the code before running it on anything sensitive. The only things
that ever reach stdout are integers, floats derived from counts, and
fixed strings defined in this file.
"""

from __future__ import annotations

import argparse
import statistics
from collections import Counter
from pathlib import Path

from pypdf import PdfReader

PT_PER_INCH = 72.0


def _orientation(width: float, height: float) -> str:
    ratio = width / height if height else 0
    if ratio > 1.55:
        return "landscape 16:9-ish (slide deck)"
    if ratio > 1.05:
        return "landscape 4:3-ish (slide deck)"
    if ratio < 0.95:
        return "portrait (document)"
    return "square"


def inspect(path: Path) -> None:
    reader = PdfReader(str(path))
    pages = reader.pages

    sizes: Counter[tuple[int, int]] = Counter()
    orientations: Counter[str] = Counter()
    char_counts: list[int] = []
    run_counts: list[int] = []
    image_counts: list[int] = []
    largest_image: tuple[int, int] = (0, 0)
    pages_with_images = 0
    total_images = 0
    big_image_pages = 0          # an image covering >25% of the page
    sparse_pages = 0             # under 200 characters: a graphic-led slide
    y_disorder: list[float] = [] # how far text departs from top-to-bottom order

    for page in pages:
        box = page.mediabox
        width, height = float(box.width), float(box.height)
        sizes[(round(width), round(height))] += 1
        orientations[_orientation(width, height)] += 1

        runs: list[tuple[float, float, int]] = []

        def visitor(text, cm, tm, font_dict, font_size, _runs=runs):
            if not (text and text.strip()):
                return
            # The text matrix holds a position relative to the current
            # transformation matrix, not a page coordinate. Compose the
            # two, or every position reads as near-zero and the
            # reading-order measure below becomes meaningless.
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            _runs.append((float(x), float(y), len(text.strip())))

        try:
            page.extract_text(visitor_text=visitor)
        except Exception:
            pass

        char_counts.append(sum(r[2] for r in runs))
        run_counts.append(len(runs))
        if sum(r[2] for r in runs) < 200:
            sparse_pages += 1

        # Reading-order disorder: what share of consecutive text runs move
        # UP the page. Flowing prose is near zero; slide layouts are high.
        if len(runs) > 3:
            backwards = sum(1 for a, b in zip(runs, runs[1:]) if b[1] > a[1] + 2)
            y_disorder.append(backwards / (len(runs) - 1))

        try:
            images = list(page.images)
        except Exception:
            images = []
        image_counts.append(len(images))
        total_images += len(images)
        if images:
            pages_with_images += 1
        for image in images:
            try:
                w, h = image.image.size
            except Exception:
                continue
            if w * h > largest_image[0] * largest_image[1]:
                largest_image = (w, h)
            if (w / 96.0 * PT_PER_INCH) * (h / 96.0 * PT_PER_INCH) > \
                    0.25 * width * height:
                big_image_pages += 1
                break

    n = len(pages)
    print(f"pages                     {n}")
    print()
    print("PAGE GEOMETRY")
    for (w, h), count in sizes.most_common(4):
        print(f"  {w} x {h} pt  ({w/PT_PER_INCH:.1f} x {h/PT_PER_INCH:.1f} in)"
              f"   {count} page(s)   {_orientation(w, h)}")
    print()
    print("TEXT DENSITY  (characters per page)")
    if char_counts:
        print(f"  median {statistics.median(char_counts):,.0f}   "
              f"mean {statistics.mean(char_counts):,.0f}   "
              f"min {min(char_counts):,}   max {max(char_counts):,}")
        print(f"  pages under 200 chars (graphic-led): {sparse_pages} "
              f"({sparse_pages / n:.0%})")
    print()
    print("TEXT FRAGMENTATION  (separate positioned runs per page)")
    if run_counts:
        print(f"  median {statistics.median(run_counts):,.0f}   "
              f"max {max(run_counts):,}")
    if y_disorder:
        share = statistics.median(y_disorder)
        print(f"  median share of runs that move UP the page: {share:.0%}")
        print("    flowing prose is typically under 10%; slide layouts are"
              " much higher,")
        print("    which means extracted text arrives out of reading order.")
    print()
    print("IMAGES")
    print(f"  total embedded images     {total_images}")
    print(f"  pages containing an image {pages_with_images} "
          f"({pages_with_images / n:.0%})")
    print(f"  pages where an image covers >25% of the page: {big_image_pages}")
    if largest_image != (0, 0):
        print(f"  largest image             {largest_image[0]} x "
              f"{largest_image[1]} px")
    print()
    print("READING")
    if sparse_pages / n > 0.3 and pages_with_images / n > 0.3:
        print("  Looks graphic-led: many pages carry little text and an image.")
        print("  Numbers shown only inside those images are NOT in the file")
        print("  and cannot be extracted without OCR or a vision model.")
    elif pages_with_images / n > 0.3:
        print("  Images are common but pages still carry text. Charts are")
        print("  probably vector with real text labels: extractable, but")
        print("  arriving as scattered fragments.")
    else:
        print("  Largely text. Extraction should recover most content,")
        print("  subject to reading order.")
    print()
    print("Nothing above is content from the document. Only counts,")
    print("dimensions, and the fixed sentences written in this file.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    inspect(args.path)


if __name__ == "__main__":
    main()
