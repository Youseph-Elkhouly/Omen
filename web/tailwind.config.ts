import type { Config } from 'tailwindcss';
const config: Config = {content:['./app/**/*.{ts,tsx}','./components/**/*.{ts,tsx}'],theme:{extend:{colors:{ink:'#07080B',glass:'rgba(255,255,255,.04)'},fontFamily:{sans:['Arial','sans-serif'],mono:['ui-monospace','monospace']}}},plugins:[]}; export default config;
