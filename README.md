# HCPt resource counter

HCP Terraform の RUM (Resource Under Management) 数をカウントして Slack に投稿するツールです。

![Slck への投稿例](slack-post-example.png)

実行環境に Azure Functions を使っています。
Azure Developer CLI (azd) を使って環境構築できます。

## 必要なもの

- 投稿先 Slack チャンネルの Incoming Webhook 設定
- HCP Terraform 用トークン
  - アカウントトークン or Organization トークン
- Azure Functions

## トリガー

- [Timer](https://learn.microsoft.com/ja-jp/azure/azure-functions/functions-bindings-timer)
  - 指定時刻に起動して Slack に投稿するトリガー
  - `function_app.py` 内で時刻指定
- HTTP
  - GET
    - HCP Terraform の RUM 数を応答するトリガー
  - POST
    - HCP Terraform の RUM 数を Slack に投稿するトリガー

## 環境変数

Azure Functions の環境変数に以下を設定します。

| 環境変数 | 値 |
| --- | --- |
| SLACK_WEBHOOK | 投稿先 Slack チャンネルの Incoming Webhook URL |
| TF_ORGANIZATION | HCP Terraform の Organization 名 |
| TF_TOKEN | HCP Terraform トークン |

## Azure Developer CLI による環境構築

このツールは Azure Developer CLI の [functions-quickstart-python-http-azd](https://github.com/Azure-Samples/functions-quickstart-python-http-azd) テンプレートを使って実行環境を構築できます。

作成される Azure Functions は [Flex Consumption プラン](https://learn.microsoft.com/ja-jp/azure/azure-functions/flex-consumption-plan)です。
日本リージョンに構築できない（2025 年 2 月時点）などの Flex Consumption プラン特有の制約があります。

`azd` を使って Azure リソースを作成します。

```shell
azd up
```

VNet を作成しない場合は `SKIP_VNET` に `true` を設定します。
この場合、`azd up` で作成されるストレージアカウントはパブリックアクセス可能な設定となります。

```bash
azd env set SKIP_VNET true
azd up
```

Azure リソース作成後、Azure Functions に関数をデプロイできます。

```bash
azd deploy
```

## HTTP トリガーの例

Azure Functions の HTTP を利用例です。

関数のエンドポイントを表示します。

```bash
export APP_NAME=$(azd env get-value AZURE_FUNCTION_NAME)
func azure functionapp list-functions $APP_NAME --show-keys
```

### GET

Azure Functions の環境変数で指定された HCP Terraform の RUM 数を応答します。

```bash
$ curl "<HTTP_GET_URL>"
{
  "total_resources": 13,
  "active_workspaces": 2,
  "timestamp": "2025-02-15 04:24:24",
  "workspaces": [
    {
      "name": "home-lab",
      "count": 8,
      "status": "active"
    },
    {
      "name": "azure-terraform-cloud-example",
      "count": 5,
      "status": "active"
    }
  ]
}
```

### POST

Azure Functions の環境変数で指定された HCP Terraform の RUM 数をリクエストボディで指定された Slack チャンネルに投稿します。

```bash
$ curl -X POST "<HTTP_POST_URL>" -H "Content-Type: application/json" -d '{"slack_webhook": "<SLACK_WEBHOOK>"}'
{
  "total_resources": 13,
  "active_workspaces": 2,
  "timestamp": "2025-02-15 04:24:24",
  "workspaces": [
    {
      "name": "home-lab",
      "count": 8,
      "status": "active"
    },
    {
      "name": "azure-terraform-cloud-example",
      "count": 5,
      "status": "active"
    }
  ]
}
```
