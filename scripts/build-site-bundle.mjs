import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const icons = fs.readFileSync(path.join(root, 'js', 'icons.js'), 'utf8');
const appData = fs.readFileSync(path.join(root, 'data', 'app-data.js'), 'utf8');
const out = `/* Generated from js/icons.js + data/app-data.js — run: npm run build:bundle */\n${icons}\n${appData}\n`;
fs.writeFileSync(path.join(root, 'js', 'site-bundle.js'), out, 'utf8');
console.log('Wrote js/site-bundle.js');
