import oled from './hardware/oled';
const disp = new oled(256, 64, true)
disp.clear()
disp.clearOverlay()
disp.blit()
