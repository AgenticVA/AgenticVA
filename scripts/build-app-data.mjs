import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dataDir = path.join(__dirname, '..', 'data');

const readJson = (name) =>
  JSON.parse(fs.readFileSync(path.join(dataDir, name), 'utf8'));

const bundle = {
  paperData: readJson('paper_data.json'),
  workflowMapping: readJson('workflow_mapping.json'),
  roles: readJson('roles.json'),
  guidanceSections: readJson('guidance_sections.json'),
};

const banner =
  '/* Generated from data/*.json — run: npm run build:data */\n';
const body = `${banner}window.__APP_DATA__ = ${JSON.stringify(bundle)};\n`;

fs.writeFileSync(path.join(dataDir, 'app-data.js'), body, 'utf8');
console.log('Wrote data/app-data.js');
