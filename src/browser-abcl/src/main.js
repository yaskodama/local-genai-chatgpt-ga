document.addEventListener("DOMContentLoaded", () => {
  document.body.innerHTML = `
  <div style="padding:16px;font-family:monospace;">
    <h2>Browser ABCL/c+</h2>
    <p style="color:#555;">Actor-based concurrent programs running in the browser.</p>
    <h3>Demos</h3>
    <ul>
      <li><a href="/rotate4lines.html">Rotate 4 Lines</a> &mdash; four actor threads rotating lines around square vertices</li>
      <li><a href="/philosophers.html">5 Dining Philosophers</a> &mdash; deadlock-free with resource hierarchy</li>
      <li><a href="/bounded_buffer.html">Bounded Buffer</a> &mdash; producer / consumer with capacity 4</li>
      <li><a href="/drone_simulator.html">Drone Return-Route Simulator</a> &mdash; MANET-style obstacle diffusion</li>
    </ul>
    <h3>Console</h3>
    <button id="openBrowserConsole">Open Browser Console</button>
  </div>
  `;
  document.getElementById("openBrowserConsole").onclick = () => {
    window.open("/browser_console.html", "_blank", "width=1000,height=700");
  };
});
