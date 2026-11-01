// Run with node tests/web/mobile-ui-check.mjs after installing the web build dependencies.
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../../', import.meta.url));
const app = join(root, 'frontends/web/app');
const require = createRequire(join(app, 'package.json'));
const { build } = require('esbuild');
const temp = await mkdtemp(join(tmpdir(), 'bc250-mobile-ui-'));
try {
  await build({
    stdin: { resolveDir: app, loader: 'jsx', contents: `
      import React from 'react';
      import assert from 'node:assert/strict';
      import {renderToStaticMarkup as render} from 'react-dom/server';
      import Gddr6 from './src/Gddr6.jsx';
      import Dashboard, {DashboardHeaderSummary} from './src/pages/Dashboard.jsx';
      import Activity from './src/DesktopActivity.jsx';
      let mobile = true;
      globalThis.matchMedia = () => ({matches: mobile});
      globalThis.document = {documentElement: {dataset: {theme: 'dark'}}};
      globalThis.__pages = {dashboard: {
        performance: {bios_version: 'P3.00', bios_variant: 'MeiMeiDXE'},
        cpu_persistence: {applied_this_boot: true, config: {valid:true, frequency:3550, scale:-28}},
        cu: {rows: [7,7,31,7].map(mask=>({mask}))}
      }, gddr6: {can_monitor:true, repository_ready:true}};
      const sample = {average_c:59.2, hotspot_c:64, chips:Array.from({length:8},(_,chip)=>({chip,temperature_c:54+chip,code:47+chip}))};
      const metrics = {cpu:{},gpu:{vram_total:512*2**20},sensors:{},memory:{},disk:{used:11*2**30,total:25*2**30}};
      globalThis.__app = {live:{metrics,gddr6:{active:true,sample:{}}},job:{kind:'gddr6.monitor',done:false,sample,sample_age:0},act:()=>{}};
      for (mobile of [true,false]) {
        let html = render(<Gddr6/>);
        for(let chip=0;chip<8;chip++) assert.ok(html.includes('Chip '+chip));
        assert.ok(html.includes(mobile ? '54.0' : '59.2'));
        if(mobile) { assert.ok(!html.includes('memory-summary'));assert.ok(!html.includes('class="hd"')); }
        else assert.ok(html.includes('64.0'));
        globalThis.__app.job.sample_age=16;
        html=render(<Gddr6/>); assert.ok(!html.includes(mobile ? '54.0' : '59.2'));
        globalThis.__app.live.gddr6.sample=sample;
        assert.ok(render(<Gddr6/>).includes(mobile ? '54.0' : '59.2'));
        globalThis.__app.live.gddr6.sample={};globalThis.__app.job.sample_age=0;
      }
      mobile=true;
      assert.equal(render(<Activity job={globalThis.__app.job} monitorVisible={true} canType={true} onClose={()=>{}}/>),'');
      assert.ok(render(<Activity job={globalThis.__app.job} monitorVisible={false} canType={true} onClose={()=>{}}/>).includes('operation-minimized'));
      let html=render(<Dashboard/>);
      assert.ok(!html.includes('AMD BC-250'),'mobile board card remains');
      const summary=render(<DashboardHeaderSummary/>);
      assert.ok(summary.includes('28') && summary.includes('512'),'CU/VRAM summary missing');
      assert.ok(!summary.includes('threads') && !summary.includes('AMD'),'extra header content');
      mobile=false;
      assert.ok(render(<Dashboard/>).includes('AMD BC-250'),'desktop board card removed');
      mobile=true;
      for(const text of ['Registered OC','3550','-28','Effective CUs','P3.00','MeiMeiDXE','25.0']) assert.ok(html.includes(text),text+' missing on mobile');
      Object.assign(metrics.sensors, {vrm_input_voltage_v:12.22, vrm_cpu_voltage_v:0.78, vrm_gpu_voltage_v:0.646,
        vrm_cpu_current_a:2.8,vrm_gpu_current_a:12,vrm_total_power_w:10});
      html=render(<Dashboard/>);
      for(const value of ['12.22','0.780','0.646','2.8','10.0']) assert.ok(html.includes(value),'telemetry value missing: '+value);
      globalThis.__app.job.sample={...sample,chips:[sample.chips[0]]};
      html=render(<Gddr6/>);
      for(let chip=0;chip<8;chip++) assert.ok(html.includes('Chip '+chip));
      assert.ok(!html.includes('NaN'));
      console.log('PASS: mobile dashboard parity; fresh, stale, collector and partial GDDR6 samples on mobile and desktop');
    `},
    bundle:true, jsx:'automatic', platform:'node', outfile:join(temp,'check.cjs'),
    nodePaths:[join(app,'node_modules')],
    plugins:[{name:'telemetry-fixture',setup(builder) {
      builder.onResolve({filter:/(^|\/)lib\.jsx$/},args=>args.namespace==='fixture'?null:{path:'lib',namespace:'fixture'});
      builder.onLoad({filter:/.*/,namespace:'fixture'},()=>({loader:'jsx',resolveDir:app,contents:
        `export * from ${JSON.stringify(join(app,'src/lib.jsx'))};export const useApp=()=>globalThis.__app;export const usePage=name=>globalThis.__pages[name];`}));
    }}],
  });
  require(join(temp,'check.cjs'));
} finally { await rm(temp,{recursive:true,force:true}); }
