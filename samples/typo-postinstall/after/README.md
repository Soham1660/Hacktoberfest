# tiny-charts

Dependency-free SVG charts in 4 kB.

## Installation

```sh
npm install tiny-charts
```

After installing you will receive a fully typed `chart()` function. No peer dependencies, no canvas, no build step.

## Usage

```js
import { chart } from "tiny-charts";

chart("#sales", { type: "bar", data: [3, 7, 4, 9] });
```

## License

MIT
