import * as fs from 'fs';

/**
 * Font data in X-GLCD format.
 * * Note:
 * Font files can be generated with the free version of MikroElektronika
 * GLCD Font Creator: www.mikroe.com/glcd-font-creator
 * The font file must be in X-GLCD 'C' format.
 */
export class XglcdFont {
  // Dict to translate bitwise values to byte position
  private static readonly BIT_POS: { [ key: number ]: number } = {
    1: 0, 2: 2, 4: 4, 8: 6, 16: 8, 32: 10, 64: 12, 128: 14, 256: 16
  };

  /** A Buffer of letters (columns consist of bytes) */
  public letters: Buffer;
  /** Maximum pixel width of font */
  public readonly width: number;
  /** Pixel height of font */
  public readonly height: number;
  /** ASCII number of first letter */
  public readonly startLetter: number;
  /** Total number of letters */
  public readonly letterCount: number;
  /** How many bytes comprises a letter (width * ceil(height/8) + 1) */
  private readonly bytesPerLetter: number;

  /**
   * Constructor for X-GLCD Font object.
   * * @param filePath Full path of font file
   * @param width Maximum width in pixels of each letter
   * @param height Height in pixels of each letter
   * @param startLetter First ASCII letter. Default is 32 (' ')
   * @param letterCount Total number of letters. Default is 96 (through 'z')
   */
  constructor(
    filePath: string,
    width: number,
    height: number,
    startLetter: number = 32,
    letterCount: number = 96
  ) {
    this.width = width;
    this.height = Math.max(height, 8); // Ensure minimum height of 8
    this.startLetter = startLetter;
    this.letterCount = letterCount;

    // Calculate bytes per letter: (floor((height - 1) / 8) + 1) * width + 1
    // This is equivalent to Math.ceil(height / 8) * width + 1
    this.bytesPerLetter = (Math.floor((this.height - 1) / 8) + 1) * this.width + 1;

    this.letters = Buffer.alloc(0); // Initialize before loading
    this.loadXglcdFont(filePath);
  }

  /**
   * Load X-GLCD font data from text file.
   * * @param filePath Full path of font file.
   */
  private loadXglcdFont(filePath: string): void {
    const bytesPerLetter = this.bytesPerLetter;
    // Buffer to hold all letter byte values
    this.letters = Buffer.alloc(bytesPerLetter * this.letterCount);
    let offset = 0;

    try {
      // Read file content synchronously
      const fileContent = fs.readFileSync(filePath, 'utf-8');
      const lines = fileContent.split('\n');

      for (const line of lines) {
        let trimmedLine = line.trim();

        // Skip lines that do not start with hex values (0x)
        if (trimmedLine.length === 0 || trimmedLine.substring(0, 2) !== '0x') {
          continue;
        }

        // Remove comments
        const commentIndex = trimmedLine.indexOf('//');
        if (commentIndex !== -1) {
          trimmedLine = trimmedLine.substring(0, commentIndex).trim();
        }

        // Remove trailing commas
        if (trimmedLine.endsWith(',')) {
          trimmedLine = trimmedLine.substring(0, trimmedLine.length - 1);
        }

        // Convert hex strings to byte values and insert into letters buffer
        const hexStrings = trimmedLine.split(',');
        const byteValues: number[] = [];

        for (const hexStr of hexStrings) {
          const trimmedHex = hexStr.trim();
          if (trimmedHex) {
            // parseInt(string, 16) converts a hex string to an integer
            byteValues.push(parseInt(trimmedHex, 16));
          }
        }

        const byteBuffer = Buffer.from(byteValues);

        // Copy the byte buffer into the main letters buffer
        if (offset + byteBuffer.length <= this.letters.length) {
          byteBuffer.copy(this.letters, offset);
          offset += bytesPerLetter;
        } else {
          // Handle case where line data is unexpected size
          console.warn(`Line data size mismatch or buffer overflow.`);
          break;
        }
      }

    } catch (error) {
      console.error(`Error loading font file: ${error}`);
      // In a real application, you might want to throw the error
    }
  }

  /**
   * Generator to return positions of 1 bits only.
   * Maps the lowest set bit to an index in BIT_POS.
   */
  private *litBits(n: number): IterableIterator<number> {
    while (n) {
      // Find the lowest set bit: b = n & (~n + 1) which is n & -n
      const b = n & -n;

      // Check if the bit position is in our lookup table
      const pos = XglcdFont.BIT_POS[ b ];
      if (pos !== undefined) {
        yield pos;
      } else {
        // Should not happen for a byte
        console.warn(`Unexpected bit value: ${b}`);
        break;
      }

      // Clear the lowest set bit: n ^= b
      n ^= b;
    }
  }

  /**
   * Convert letter byte data to pixels.
   * * @param letter Letter to return (must exist within font).
   * @param color RGB565 color value.
   * @param background RGB565 background color (default: black/0).
   * @param landscape Orientation (default: false = portrait)
   * @returns [pixelData, letterWidth, letterHeight]
   */
  public getLetter(
    letter: string,
    color: number,
    background: number = 0,
    landscape: boolean = false
  ): [ Buffer, number, number ] {
    // Get index of letter
    const letterOrd = letter.charCodeAt(0) - this.startLetter;

    // Confirm font contains letter
    if (letterOrd < 0 || letterOrd >= this.letterCount) {
      console.error(`Font does not contain character: ${letter}`);
      return [ Buffer.alloc(0), 0, 0 ];
    }

    const offset = letterOrd * this.bytesPerLetter;
    // Get the bytes for the specific letter (first byte is width, rest are pixel data)
    const letterBytes = this.letters.subarray(offset, offset + this.bytesPerLetter);

    // Get width of letter (specified by first byte)
    const letterWidth = letterBytes[ 0 ];
    const letterHeight = this.height;

    // Size in pixels (letter_height * letter_width)
    const letterSize = letterHeight * letterWidth;
    // Size in bytes (size * 2, for 16-bit RGB565 color)
    const bufferSize = letterSize * 2;

    let buf: Buffer;

    // Create buffer and pre-fill with background color if provided
    if (background) {
      const bg_msb = (background >> 8) & 0xFF;
      const bg_lsb = background & 0xFF;
      buf = Buffer.alloc(bufferSize);
      for (let i = 0; i < bufferSize; i += 2) {
        buf.writeUInt8(bg_msb, i);
        buf.writeUInt8(bg_lsb, i + 1);
      }
    } else {
      buf = Buffer.alloc(bufferSize); // Default is filled with 0s (black)
    }

    const msb = (color >> 8) & 0xFF;
    const lsb = color & 0xFF;

    // The pixel data starts at index 1 of letterBytes
    const pixelDataBytes = letterBytes.subarray(1);

    if (landscape) {
      // Populate buffer in order for landscape
      let pos = bufferSize - (letterHeight * 2); // Start at the end of the buffer for the first column
      let lh = letterHeight;
      let byteIndex = 0;

      // Loop through letter byte data and convert to pixel data
      for (const b of pixelDataBytes) {
        // Process only colored bits
        for (const bit of this.litBits(b)) {
          // bit is the index into the BIT_POS array (0, 2, 4, ...)
          buf.writeUInt8(msb, bit + pos);
          buf.writeUInt8(lsb, bit + pos + 1);
        }

        byteIndex++;
        if (lh > 8) {
          // This byte is the first of a multi-byte column segment
          pos += 16; // 8 bits * 2 bytes/color = 16
          lh -= 8;
        } else {
          // This is the last byte of a column. Move to start of the previous column.
          // New position = Current pos - (letter_height * 4) + (lh * 2) 
          // (The + (lh * 2) accounts for the current column's segment width)
          // The original Python logic seems flawed for multi-byte columns, 
          // but following the logic as closely as possible:
          pos -= (letterHeight * 4) - (lh * 2);
          lh = letterHeight; // Reset column height for the next column
        }
      }
    } else {
      // Populate buffer in order for portrait
      let col = 0; // Set column to first column
      const bytesPerSegment = Math.ceil(letterHeight / 8);
      let letterByteIndex = 0;

      // Loop through letter byte data and convert to pixel data
      for (const b of pixelDataBytes) {
        // Process only colored bits
        // segment_size: (0, 1, 2, ...) * letterWidth * 2 bytes/color
        const segmentSize = letterByteIndex * letterWidth * 2 * 8; // * 8 because bit is index * 2

        for (const bit of this.litBits(b)) {
          // bit is (0, 2, 4, ... 14). We need the actual pixel row index: bit / 2
          const pixelRow = bit / 2;
          // pos: (pixel_row * letter_width + column_index) * 2 bytes/color + segment_size
          let pos = (pixelRow * letterWidth + col) * 2 + segmentSize;

          buf.writeUInt8(msb, pos);
          buf.writeUInt8(lsb, pos + 1);
        }

        letterByteIndex++;
        if (letterByteIndex >= bytesPerSegment) {
          col++;
          letterByteIndex = 0;
        }
      }
    }

    return [ buf, letterWidth, letterHeight ];
  }

  /**
   * Measure length of text string in pixels.
   * * @param text Text string to measure
   * @param spacing Pixel spacing between letters. Default: 1.
   * @returns length of text
   */
  public measureText(text: string, spacing: number = 1): number {
    let length = 0;
    for (const letter of text) {
      // Get index of letter
      const letterOrd = letter.charCodeAt(0) - this.startLetter;
      if (letterOrd < 0 || letterOrd >= this.letterCount) {
        continue; // Skip characters not in the font
      }
      const offset = letterOrd * this.bytesPerLetter;

      // The width of the letter is the first byte of its data
      const letterWidth = this.letters.readUInt8(offset);

      // Add length of letter and spacing
      length += letterWidth + spacing;
    }
    return length;
  }
}

// Example usage (for Node.js):
/*
// Assuming a font file named 'my_font.txt' is in the same directory
const FONT_FILE_PATH = path.join(__dirname, 'my_font.txt'); 

try {
    // Width: 10, Height: 16. Default start_letter: 32, letter_count: 96
    const font = new XglcdFont(FONT_FILE_PATH, 10, 16); 

    const textToMeasure = "Hello World";
    const textLength = font.measureText(textToMeasure);
    console.log(`The text "${textToMeasure}" is ${textLength} pixels long.`);

    // Get pixel data for 'A' (e.g., color Red=0xF800, background Blue=0x001F)
    const [pixelBuffer, width, height] = font.getLetter('A', 0xF800, 0x001F);
    console.log(`Letter 'A' dimensions: ${width}x${height} pixels.`);
    console.log(`Pixel data buffer size: ${pixelBuffer.length} bytes.`);
} catch (e) {
    console.error("Failed to initialize font:", e);
}
*/
