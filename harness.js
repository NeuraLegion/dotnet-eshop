const express = require('express');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const app = express();
app.use(express.json({ limit: '2mb' }));
app.use(express.urlencoded({ extended: true }));

function logWarn(msg) {
  console.warn(`[harness] ${msg}`);
}

function findDotnetExe() {
  try {
    execFileSync('dotnet', ['--info'], { stdio: 'ignore' });
    return 'dotnet';
  } catch (_) {
    return null;
  }
}

function compileHarness() {
  const dotnet = findDotnetExe();
  if (!dotnet) throw new Error('dotnet not available');

  const tempDir = path.join('/tmp', `ordering-harness-${Date.now()}`);
  fs.mkdirSync(tempDir, { recursive: true });

  const csproj = `
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <OutputType>Exe</OutputType>
    <LangVersion>latest</LangVersion>
  </PropertyGroup>
</Project>`.trim();

  const program = `
using System.Text.Json;
using System.Text.Json.Serialization;

var mode = args.Length > 0 ? args[0] : "";
var json = Console.In.ReadToEnd();
var opts = new JsonSerializerOptions
{
    PropertyNameCaseInsensitive = true,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
};

try
{
    switch (mode)
    {
        case "createorderdraftcommandhandler-handle":
        {
            var message = DeserializeCreateOrderDraftCommandInput(json, opts) ?? new CreateOrderDraftCommandInput();
            var items = message.Items ?? Array.Empty<BasketItem>();

            var handler = new CreateOrderDraftCommandHandler();
            var cmd = new CreateOrderDraftCommand(message.BuyerId ?? "", items);
            var result = await handler.Handle(cmd, CancellationToken.None);

            Console.Write(JsonSerializer.Serialize(result, opts));
            break;
        }

        case "basketitemextensions-toorderitemdto":
        {
            var item = DeserializeBasketItemInput(json, opts) ?? new BasketItem();
            var result = BasketItemExtensions.ToOrderItemDTO(item);
            Console.Write(JsonSerializer.Serialize(result, opts));
            break;
        }

        case "basketitemextensions-toorderitemsdto":
        {
            var items = DeserializeBasketItemsInput(json, opts);
            var result = BasketItemExtensions.ToOrderItemsDTO(items).ToArray();
            Console.Write(JsonSerializer.Serialize(result, opts));
            break;
        }

        default:
            throw new Exception("Unknown mode");
    }
}
catch (Exception ex)
{
    Console.Error.WriteLine(ex.ToString());
    Environment.Exit(1);
}

static CreateOrderDraftCommandInput? DeserializeCreateOrderDraftCommandInput(string json, JsonSerializerOptions opts)
{
    if (string.IsNullOrWhiteSpace(json) || json.Trim() == "null")
        return null;

    using var doc = JsonDocument.Parse(json);
    var root = doc.RootElement;

    if (root.ValueKind != JsonValueKind.Object)
        throw new JsonException("Expected object input for CreateOrderDraftCommandHandler.Handle.");

    if (TryGetPropertyIgnoreCase(root, "message", out var messageProp) && messageProp.ValueKind == JsonValueKind.Object)
        return JsonSerializer.Deserialize<CreateOrderDraftCommandInput>(messageProp.GetRawText(), opts);

    return JsonSerializer.Deserialize<CreateOrderDraftCommandInput>(json, opts);
}

static BasketItem? DeserializeBasketItemInput(string json, JsonSerializerOptions opts)
{
    if (string.IsNullOrWhiteSpace(json) || json.Trim() == "null")
        return null;

    using var doc = JsonDocument.Parse(json);
    var root = doc.RootElement;

    if (root.ValueKind == JsonValueKind.Object)
    {
        if (TryGetPropertyIgnoreCase(root, "item", out var itemProp) && itemProp.ValueKind == JsonValueKind.Object)
            return JsonSerializer.Deserialize<BasketItem>(itemProp.GetRawText(), opts);

        return JsonSerializer.Deserialize<BasketItem>(json, opts);
    }

    throw new JsonException("Expected BasketItem object input.");
}

static BasketItem[] DeserializeBasketItemsInput(string json, JsonSerializerOptions opts)
{
    if (string.IsNullOrWhiteSpace(json) || json.Trim() == "null")
        return Array.Empty<BasketItem>();

    using var doc = JsonDocument.Parse(json);
    var root = doc.RootElement;

    if (root.ValueKind == JsonValueKind.Array)
    {
        return JsonSerializer.Deserialize<BasketItem[]>(json, opts) ?? Array.Empty<BasketItem>();
    }

    if (root.ValueKind == JsonValueKind.Object)
    {
        if (TryGetPropertyIgnoreCase(root, "basketItems", out var basketItems) && basketItems.ValueKind == JsonValueKind.Array)
            return JsonSerializer.Deserialize<BasketItem[]>(basketItems.GetRawText(), opts) ?? Array.Empty<BasketItem>();

        if (TryGetPropertyIgnoreCase(root, "items", out var items) && items.ValueKind == JsonValueKind.Array)
            return JsonSerializer.Deserialize<BasketItem[]>(items.GetRawText(), opts) ?? Array.Empty<BasketItem>();
    }

    throw new JsonException("Expected BasketItem[] input or wrapper object containing basketItems/items.");
}

static bool TryGetPropertyIgnoreCase(JsonElement element, string name, out JsonElement value)
{
    foreach (var prop in element.EnumerateObject())
    {
        if (string.Equals(prop.Name, name, StringComparison.OrdinalIgnoreCase))
        {
            value = prop.Value;
            return true;
        }
    }

    value = default;
    return false;
}

public sealed class CreateOrderDraftCommandHandler
{
    public Task<OrderDraftDTO> Handle(CreateOrderDraftCommand message, CancellationToken cancellationToken)
    {
        var order = Order.NewDraft();
        var orderItems = message.Items.Select(i => i.ToOrderItemDTO());
        foreach (var item in orderItems)
        {
            order.AddOrderItem(item.ProductId, item.ProductName, item.UnitPrice, item.Discount, item.PictureUrl, item.Units);
        }

        return Task.FromResult(OrderDraftDTO.FromOrder(order));
    }
}

public static class BasketItemExtensions
{
    public static IEnumerable<OrderItemDTO> ToOrderItemsDTO(this IEnumerable<BasketItem> basketItems)
    {
        foreach (var item in basketItems)
        {
            yield return item.ToOrderItemDTO();
        }
    }

    public static OrderItemDTO ToOrderItemDTO(this BasketItem item)
    {
        return new OrderItemDTO()
        {
            ProductId = item.ProductId,
            ProductName = item.ProductName,
            PictureUrl = item.PictureUrl,
            UnitPrice = item.UnitPrice,
            Units = item.Quantity
        };
    }
}

public sealed record CreateOrderDraftCommand(string BuyerId, IEnumerable<BasketItem> Items);

public sealed class BasketItem
{
    public string? Id { get; init; }
    public int ProductId { get; init; }
    public string? ProductName { get; init; }
    public decimal UnitPrice { get; init; }
    public decimal OldUnitPrice { get; init; }
    public int Quantity { get; init; }
    public string? PictureUrl { get; init; }
}

public sealed record OrderDraftDTO
{
    public IEnumerable<OrderItemDTO> OrderItems { get; init; } = Array.Empty<OrderItemDTO>();
    public decimal Total { get; init; }

    public static OrderDraftDTO FromOrder(Order order)
    {
        return new OrderDraftDTO()
        {
            OrderItems = order.OrderItems.Select(oi => new OrderItemDTO
            {
                Discount = oi.Discount,
                ProductId = oi.ProductId,
                UnitPrice = oi.UnitPrice,
                PictureUrl = oi.PictureUrl,
                Units = oi.Units,
                ProductName = oi.ProductName
            }),
            Total = order.GetTotal()
        };
    }
}

public sealed record OrderItemDTO
{
    public int ProductId { get; init; }
    public string? ProductName { get; init; }
    public decimal UnitPrice { get; init; }
    public decimal Discount { get; init; }
    public int Units { get; init; }
    public string? PictureUrl { get; init; }
}

public sealed class Order
{
    private readonly List<OrderItem> _orderItems = new();
    private bool _isDraft;

    public IReadOnlyCollection<OrderItem> OrderItems => _orderItems.AsReadOnly();

    public static Order NewDraft()
    {
        var order = new Order
        {
            _isDraft = true
        };
        return order;
    }

    public void AddOrderItem(int productId, string? productName, decimal unitPrice, decimal discount, string? pictureUrl, int units = 1)
    {
        var existingOrderForProduct = _orderItems.SingleOrDefault(o => o.ProductId == productId);

        if (existingOrderForProduct != null)
        {
            if (discount > existingOrderForProduct.Discount)
            {
                existingOrderForProduct.SetNewDiscount(discount);
            }

            existingOrderForProduct.AddUnits(units);
        }
        else
        {
            var orderItem = new OrderItem(productId, productName, unitPrice, discount, pictureUrl, units);
            _orderItems.Add(orderItem);
        }
    }

    public decimal GetTotal() => _orderItems.Sum(o => o.Units * o.UnitPrice);
}

public sealed class OrderItem
{
    public int ProductId { get; }
    public string? ProductName { get; }
    public decimal UnitPrice { get; }
    public decimal Discount { get; private set; }
    public int Units { get; private set; }
    public string? PictureUrl { get; }

    public OrderItem(int productId, string? productName, decimal unitPrice, decimal discount, string? pictureUrl, int units)
    {
        if (units <= 0)
        {
            throw new Exception("Invalid number of units");
        }

        if ((unitPrice * units) < discount)
        {
            throw new Exception("The total of order item is lower than applied discount");
        }

        ProductId = productId;
        ProductName = productName;
        UnitPrice = unitPrice;
        Discount = discount;
        PictureUrl = pictureUrl;
        Units = units;
    }

    public void SetNewDiscount(decimal discount)
    {
        if (discount < 0)
        {
            throw new Exception("Discount is not valid");
        }

        Discount = discount;
    }

    public void AddUnits(int units)
    {
        if (units < 0)
        {
            throw new Exception("Invalid units");
        }

        Units += units;
    }
}

public sealed class CreateOrderDraftCommandInput
{
    public string? BuyerId { get; init; }
    public BasketItem[]? Items { get; init; }
}
`.trim();

  fs.writeFileSync(path.join(tempDir, 'Harness.csproj'), csproj);
  fs.writeFileSync(path.join(tempDir, 'Program.cs'), program);

  try {
    execFileSync(
      dotnet,
      ['build', path.join(tempDir, 'Harness.csproj'), '-c', 'Release', '-o', path.join(tempDir, 'out')],
      {
        stdio: 'pipe',
        cwd: tempDir,
        maxBuffer: 20 * 1024 * 1024
      }
    );
  } catch (e) {
    const stderr = e && e.stderr ? e.stderr.toString() : '';
    const stdout = e && e.stdout ? e.stdout.toString() : '';
    throw new Error(`Failed to build C# harness: ${stderr || stdout || e.message}`);
  }

  const dll = path.join(tempDir, 'out', 'Harness.dll');

  return {
    run(mode, body) {
      try {
        const out = execFileSync(dotnet, [dll, mode], {
          input: JSON.stringify(body == null ? null : body),
          encoding: 'utf8',
          cwd: tempDir,
          maxBuffer: 20 * 1024 * 1024
        });
        return { ok: true, out };
      } catch (e) {
        return {
          ok: false,
          err:
            (e && e.stderr ? e.stderr.toString() : '') ||
            (e && e.stdout ? e.stdout.toString() : '') ||
            e.message
        };
      }
    }
  };
}

let runner = null;
try {
  runner = compileHarness();
  logWarn('C# harness compiled successfully');
} catch (e) {
  logWarn(`C# harness unavailable: ${e.message}`);
}

app.get('/health', (req, res) => {
  res.type('text/plain').status(200).send('ok');
});

function textReply(res, status, body) {
  res.type('text/plain').status(status).send(String(body));
}

function route(mode) {
  return (req, res) => {
    try {
      if (!runner) {
        return textReply(res, 500, 'harness not available');
      }

      const result = runner.run(mode, req.body);
      if (!result.ok) {
        return textReply(res, 500, result.err);
      }

      return textReply(res, 200, result.out);
    } catch (e) {
      return textReply(res, 500, e && e.message ? e.message : String(e));
    }
  };
}

app.post('/harness/createorderdraftcommandhandler-handle', route('createorderdraftcommandhandler-handle'));
app.post('/harness/basketitemextensions-toorderitemdto', route('basketitemextensions-toorderitemdto'));
app.post('/harness/basketitemextensions-toorderitemsdto', route('basketitemextensions-toorderitemsdto'));

const port = parseInt(process.env.PORT || '3001', 10);
app.listen(port, '0.0.0.0', () => {
  console.log(`Harness listening on ${port}`);
});
