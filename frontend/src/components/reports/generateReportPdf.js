import jsPDF from "jspdf";
import html2canvas from "html2canvas";

// Renders a DOM node (the printable report) to a paginated A4 PDF. Snapshotting
// the browser-rendered node means Arabic shaping + RTL come out correct — jsPDF's
// built-in fonts can't shape Arabic on their own.
//
// Naive slicing (redraw the same full-height image shifted up by a fixed
// page-height each page) cuts straight through whatever DOM content happens
// to sit at that pixel boundary — a table row split in half, a text line
// sheared off flush against the next page's top edge (reads as
// "overlapping" since there's zero margin there). Instead, walk the canvas
// near each page-height boundary and slice at the nearest row that's
// actually blank (uniform color, no text/border pixels), so every page
// break falls in real whitespace between sections/rows, and give every
// page after the first a small top margin so a slice never starts flush
// against the edge.
const PAGE_TOP_MARGIN_PT = 24;
const SLICE_SEARCH_WINDOW_PX = 140; // how far to look, up or down, from the ideal boundary for a blank row (source-canvas px, already 2x-scaled)
const BLANK_ROW_VARIANCE = 10; // max per-channel (max-min) spread across a row to call it "blank"

function isRowBlank(ctx, canvasWidth, y) {
  const { data } = ctx.getImageData(0, y, canvasWidth, 1);
  let rMin = 255, rMax = 0, gMin = 255, gMax = 0, bMin = 255, bMax = 0;
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i], g = data[i + 1], b = data[i + 2];
    if (r < rMin) rMin = r;
    if (r > rMax) rMax = r;
    if (g < gMin) gMin = g;
    if (g > gMax) gMax = g;
    if (b < bMin) bMin = b;
    if (b > bMax) bMax = b;
  }
  return rMax - rMin <= BLANK_ROW_VARIANCE && gMax - gMin <= BLANK_ROW_VARIANCE && bMax - bMin <= BLANK_ROW_VARIANCE;
}

// Best row to cut at near `idealY` — searches outward so pages stay close to
// a full page's worth of content, preferring the closest blank row. Falls
// back to idealY itself if nothing blank is found in the window (only
// happens if a single section is taller than one full page, which doesn't
// occur in this report).
function findSliceY(ctx, canvasWidth, canvasHeight, idealY) {
  const clampedIdeal = Math.min(idealY, canvasHeight - 1);
  for (let offset = 0; offset <= SLICE_SEARCH_WINDOW_PX; offset++) {
    const below = clampedIdeal + offset;
    if (below <= canvasHeight - 1 && isRowBlank(ctx, canvasWidth, below)) return below;
    const above = clampedIdeal - offset;
    if (above >= 0 && isRowBlank(ctx, canvasWidth, above)) return above;
  }
  return clampedIdeal;
}

export async function generateReportPdf(node, filename = "novera-screening.pdf") {
  const canvas = await html2canvas(node, {
    scale: 2,
    backgroundColor: "#ffffff",
    useCORS: true,
    logging: false,
  });

  const pdf = new jsPDF({ unit: "pt", format: "a4" });
  const pageW = pdf.internal.pageSize.getWidth();
  const pageH = pdf.internal.pageSize.getHeight();

  const pxPerPt = canvas.width / pageW; // source-canvas px per PDF pt, at full page width
  const ctx = canvas.getContext("2d");

  let sliceStartPx = 0;
  let firstPage = true;

  while (sliceStartPx < canvas.height - 1) {
    const availablePt = firstPage ? pageH : pageH - PAGE_TOP_MARGIN_PT;
    const idealEndPx = sliceStartPx + availablePt * pxPerPt;
    const sliceEndPx =
      idealEndPx >= canvas.height ? canvas.height : findSliceY(ctx, canvas.width, canvas.height, idealEndPx);
    const sliceHeightPx = Math.max(1, sliceEndPx - sliceStartPx);

    const pageCanvas = document.createElement("canvas");
    pageCanvas.width = canvas.width;
    pageCanvas.height = sliceHeightPx;
    pageCanvas
      .getContext("2d")
      .drawImage(canvas, 0, sliceStartPx, canvas.width, sliceHeightPx, 0, 0, canvas.width, sliceHeightPx);

    if (!firstPage) pdf.addPage();
    const yOffsetPt = firstPage ? 0 : PAGE_TOP_MARGIN_PT;
    pdf.addImage(pageCanvas.toDataURL("image/png"), "PNG", 0, yOffsetPt, pageW, sliceHeightPx / pxPerPt);

    sliceStartPx = sliceEndPx;
    firstPage = false;
  }

  pdf.save(filename);
}
