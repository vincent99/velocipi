import { Canvas } from 'skia-canvas/lib';
import oled from './lib/oled';
const canvas = new Canvas(256, 64)
const disp = new oled(canvas, true)
disp.close()
