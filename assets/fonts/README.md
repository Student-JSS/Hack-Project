# Fonts for the PDF packet

reportlab's built-in Helvetica font cannot render Devanagari, so a Hindi complaint
draft would print as empty boxes in the exported PDF.

To fix that, drop a Devanagari TTF here and rebuild the packet:

1. Download **Noto Sans Devanagari** (SIL Open Font License) from
   <https://fonts.google.com/noto/specimen/Noto+Sans+Devanagari>.
2. Save the `.ttf` file in this folder (for example `NotoSansDevanagari-Regular.ttf`).
3. Restart the app and export the packet again.

`src/pdf_export.py` registers the first `.ttf` it finds in this folder as the
font `SaakshyaDevanagari` and uses it automatically. If no font is present the
PDF still builds, but it prints a warning on the cover page: Hindi text may not
display correctly, so use the English version for printing.

The font file is not bundled with this repository to keep the download small and
to avoid shipping a font without its license file. If you add one, add its
license text here as well.
