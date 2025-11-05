import { test, before, after } from 'node:test';
import { SecRunner } from '@sectester/runner';
import { AttackParamLocation, HttpMethod } from '@sectester/scan';

const timeout = 40 * 60 * 1000;
const baseUrl = process.env.BRIGHT_TARGET_URL!;

let runner!: SecRunner;

before(async () => {
  runner = new SecRunner({
    hostname: process.env.BRIGHT_HOSTNAME!,
    projectId: process.env.BRIGHT_PROJECT_ID!
  });

  await runner.init();
});

after(() => runner.clear());

test('POST /api/catalog/items', { signal: AbortSignal.timeout(timeout) }, async () => {
  await runner
    .createScan({
      tests: ['bopla', 'file_upload', 'sqli', 'xss', 'osi'],
      attackParamLocations: [AttackParamLocation.BODY],
      starMetadata: {
        "code_source": "NeuraLegion/dotnet-eshop:main",
        "databases": ["PostgreSQL"]
      }
    })
    .setFailFast(false)
    .timeout(timeout)
    .run({
      method: HttpMethod.POST,
      url: `${baseUrl}/api/catalog/items`,
      body: {
        Name: "Sample Item",
        Description: "A sample catalog item description.",
        Price: 19.99,
        PictureFileName: "sample.jpg",
        CatalogTypeId: 1,
        CatalogBrandId: 1,
        AvailableStock: 100,
        RestockThreshold: 10,
        MaxStockThreshold: 1000,
        OnReorder: false
      },
      headers: { 'Content-Type': 'application/json' }
    });
});