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

test('PUT /api/catalog/items?api-version=1.0', { signal: AbortSignal.timeout(timeout) }, async () => {
  await runner
    .createScan({
      tests: [
        'id_enumeration',
        'bopla',
        'business_constraint_bypass',
        'xss',
        'html_injection',
        'lfi',
        'full_path_disclosure',
        'improper_asset_management'
      ],
      attackParamLocations: [AttackParamLocation.BODY, AttackParamLocation.QUERY],
      starMetadata: {
        code_source: 'NeuraLegion/dotnet-eshop:main',
        databases: ['PostgreSQL', 'Redis'],
        user_roles: []
      },
      poolSize: +process.env.SECTESTER_SCAN_POOL_SIZE || undefined
    })
    .setFailFast(false)
    .timeout(timeout)
    .run({
      method: HttpMethod.PUT,
      url: `${baseUrl}/api/catalog/items?api-version=1.0`,
      body: {
        id: 1,
        name: '.NET Bot Black Hoodie',
        description: 'Official eShop hoodie in black.',
        price: 19.5,
        pictureFileName: '1.png',
        catalogTypeId: 2,
        catalogType: {
          id: 2,
          type: 'T-Shirt'
        },
        catalogBrandId: 1,
        catalogBrand: {
          id: 1,
          brand: '.NET'
        },
        availableStock: 100,
        restockThreshold: 10,
        maxStockThreshold: 200,
        onReorder: false
      },
      headers: { 'Content-Type': 'application/json' }
    });
});