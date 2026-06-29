// Renders the exact TRC tally device artwork (from tally.svg) lit per firmware
// state code. The geometry below is copied verbatim from the designed SVG; only
// the LED colours, the halo glow, and the input-number badge change with state.
//
// Codes: 0 off, 1 program(red), 2 preview(green), 3 rec, 4 stream,
//        5 preview operator-only, 9 identify, 10 idle(white).

// Exact LED dot positions (st7 circles, r=2.63) from tally.svg.
const LED_POS = [
  [103.1, 108.88], [125.34, 108.88], [147.59, 108.88],
  [80.85, 123.19], [103.1, 123.19], [125.34, 123.19], [147.59, 123.19], [169.83, 123.19],
  [80.85, 137.51], [103.1, 137.51], [125.34, 137.51], [147.59, 137.51], [169.83, 137.51],
  [80.85, 151.82], [103.1, 151.82], [125.34, 151.82], [147.59, 151.82], [169.83, 151.82],
  [80.85, 166.13], [103.1, 166.13], [125.34, 166.13], [147.59, 166.13], [169.83, 166.13],
];

// Exact halo glow shapes (the blurred FF0000 elements) from tally.svg.
const GLOW_SHAPES = [
  '<ellipse cx="124.21" cy="67.18" rx="46.39" ry="15.97"/>',
  '<ellipse transform="matrix(0.7071 -0.7071 0.7071 0.7071 -44.9829 77.0974)" cx="70.57" cy="92.85" rx="43.14" ry="21.27"/>',
  '<path d="M51.58,110.17c10.12,0,18.33,15.95,18.33,35.62s-8.21,35.62-18.33,35.62s-18.33-15.95-18.33-35.62S41.46,110.17,51.58,110.17z"/>',
  '<path d="M51.06,152.08c10.12,0,18.33,17.33,18.33,38.71s-8.21,38.71-18.33,38.71s-18.33-17.33-18.33-38.71S40.94,152.08,51.06,152.08z"/>',
  '<ellipse cx="88.13" cy="216.24" rx="38.25" ry="18.33"/>',
  '<ellipse transform="matrix(0.7071 -0.7071 0.7071 0.7071 -11.5398 154.7751)" cx="181.06" cy="91.32" rx="20.71" ry="43.14"/>',
  '<ellipse cx="200.45" cy="144.87" rx="18.33" ry="35.62"/>',
  '<ellipse cx="199.97" cy="189.35" rx="18.33" ry="39.23"/>',
  '<ellipse cx="157.9" cy="216.32" rx="38.25" ry="18.33"/>',
].join("");

const STATE = {
  0:  { led: "#1A1A1A", glow: null,      anim: null },
  1:  { led: "#FF1F1F", glow: "#FF0000", anim: null },
  2:  { led: "#19E36A", glow: "#00C853", anim: null },
  3:  { led: "#FF1F1F", glow: "#FF0000", anim: "blink" },
  4:  { led: "#D633E0", glow: "#C026D3", anim: "blink" },
  5:  { led: "#19E36A", glow: "#00C853", anim: null, opOnly: true },
  9:  { led: "#FFFFFF", glow: "#FF0000", anim: "pulse" },
  10: { led: "#F2F2F2", glow: "#BBBBBB", anim: null },
};

let _uid = 0;

function renderTallyDevice(code, inputId) {
  const s = STATE[code] || STATE[0];
  const fid = "tdblur" + (_uid++);
  const animClass = s.anim ? ` td-${s.anim}` : "";

  let glow = "";
  if (s.glow) {
    glow = `<g class="td-glow${animClass}" fill="${s.glow}" filter="url(#${fid})">${GLOW_SHAPES}</g>`;
  }

  const dots = LED_POS.map(([x, y]) => {
    const lit = !s.opOnly || x <= 103.1;  // operator-side columns only for code 5
    return `<circle cx="${x}" cy="${y}" r="2.63" fill="${lit ? s.led : "#1A1A1A"}"/>`;
  }).join("");

  const num = inputId == null ? "" : String(inputId);
  return `<svg viewBox="0 0 250 250" width="100%" role="img" aria-label="tally state ${code}">
    <defs><filter id="${fid}" x="-10" y="-10" width="270" height="270">
      <feGaussianBlur in="SourceGraphic" stdDeviation="10"/></filter></defs>
    ${glow}
    <path fill="#282828" d="M131.29,242.81h-12.76c-1.86,0-3.36-1.5-3.36-3.36V216.8c0-1.86,1.5-3.36,3.36-3.36h12.76c1.86,0,3.36,1.5,3.36,3.36v22.66C134.65,241.31,133.15,242.81,131.29,242.81z"/>
    <path fill="#333333" d="M200.99,141.74v51.25c0,13.08-10.61,23.69-23.69,23.69H74.68c-13.08,0-23.69-10.61-23.69-23.69v-51.25c0-41.42,33.58-75,75-75S200.99,100.32,200.99,141.74z"/>
    <g class="td-leds${animClass}">${dots}</g>
    <rect x="112.45" y="182.77" width="25.11" height="25.11" rx="2" fill="#1A1A1A" stroke="${s.led}" stroke-miterlimit="10"/>
    <text x="125" y="201.5" text-anchor="middle" font-size="18" font-family="sans-serif" fill="#F2F2F2">${num}</text>
  </svg>`;
}

window.renderTallyDevice = renderTallyDevice;
