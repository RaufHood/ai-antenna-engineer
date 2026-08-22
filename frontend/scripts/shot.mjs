import { chromium } from "playwright";

const errors = [];
const browser = await chromium.launch({
  args: [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
  ],
});
const page = await browser.newPage({ viewport: { width: 1680, height: 1000 } });
page.on("console", (m) => {
  if (m.type() === "error") errors.push(m.text());
});
page.on("pageerror", (e) => errors.push("pageerror: " + e.message));

await page.goto("http://localhost:3000/", { waitUntil: "networkidle" });
await page.waitForTimeout(4000);
await page.screenshot({ path: "shots/01-idle.png" });

await page.getByRole("button", { name: "Run placement study" }).click();
await page.waitForTimeout(9000);
await page.screenshot({ path: "shots/02-running.png" });

await page.waitForTimeout(16000);
await page.screenshot({ path: "shots/03-done.png" });

// Heatmap + back view
await page.getByRole("button", { name: "Heatmap", exact: true }).click();
await page.getByRole("button", { name: "Back", exact: true }).click();
await page.waitForTimeout(2500);
await page.screenshot({ path: "shots/04-heatmap.png" });

// Exploded view
await page.getByRole("button", { name: "Iso", exact: true }).click();
await page.getByRole("button", { name: "Heatmap", exact: true }).click();
const slider = page.locator('input[type="range"]');
await slider.evaluate((el) => {
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    "value",
  ).set;
  setter.call(el, "0.75");
  el.dispatchEvent(new Event("input", { bubbles: true }));
});
await page.waitForTimeout(2500);
await page.screenshot({ path: "shots/05-exploded.png" });

console.log("console errors:", errors.length ? errors : "none");
await browser.close();
