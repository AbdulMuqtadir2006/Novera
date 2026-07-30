import jsPDF from "jspdf";
import html2canvas from "html2canvas";

// Renders a DOM node (the printable report) to a paginated A4 PDF. Snapshotting
// the browser-rendered node means Arabic shaping + RTL come out correct — jsPDF's
// built-in fonts can't shape Arabic on their own.
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

  const imgW = pageW;
  const imgH = (canvas.height * imgW) / canvas.width;

  let heightLeft = imgH;
  let position = 0;
  const imgData = canvas.toDataURL("image/png");

  pdf.addImage(imgData, "PNG", 0, position, imgW, imgH);
  heightLeft -= pageH;

  while (heightLeft > 0) {
    position -= pageH;
    pdf.addPage();
    pdf.addImage(imgData, "PNG", 0, position, imgW, imgH);
    heightLeft -= pageH;
  }

  pdf.save(filename);
}
