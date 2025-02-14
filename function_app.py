import azure.functions as func
import logging
from datetime import datetime
from datetime import timezone
import pytz
import os
from typing import Dict, List, Optional, Tuple

import requests

# 共通の定数定義
class Constants:
    """アプリケーション全体で使用する定数"""
    STATUS_ICONS = {
        "active": "✅",
        "no_state": "🈳",
        "error": "⚠️",
        "unknown": "❓"
    }
    
    STATUS = {
        "ACTIVE": "active",
        "NO_STATE": "no_state",
        "NO_RESOURCES": "no_resources",
        "ERROR": "error"
    }
    
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
    API_BASE = "https://app.terraform.io/api/v2"
    JST = pytz.timezone('Asia/Tokyo')

class TerraformAPI:
    def __init__(self, token: str, organization: str):
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/vnd.api+json"
        }
        self.organization = organization

    def get_all_workspaces(self) -> List[Dict]:
        """組織内のすべてのワークスペースを取得"""
        all_workspaces = []
        next_url = f"{Constants.API_BASE}/organizations/{self.organization}/workspaces"
        
        while next_url:
            logging.info(f"Fetching workspaces from: {next_url}")
            response = requests.get(next_url, headers=self.headers)
            response.raise_for_status()
            
            data = response.json()
            all_workspaces.extend(data["data"])
            next_url = data.get("links", {}).get("next")
        
        return all_workspaces

    def get_workspace_resources(self, workspace_id: str, workspace_name: str) -> Dict:
        """ワークスペースのリソース情報を取得"""
        try:
            state_url = f"{Constants.API_BASE}/workspaces/{workspace_id}/current-state-version"
            response = requests.get(state_url, headers=self.headers)
            
            if response.status_code == 404:
                return {"name": workspace_name, "count": 0, "status": Constants.STATUS["NO_STATE"]}
            
            if response.status_code == 200:
                state_data = response.json()["data"]
                if (state_data and 
                    "attributes" in state_data and 
                    "billable-rum-count" in state_data["attributes"]):
                    count = state_data["attributes"]["billable-rum-count"]
                    return {
                        "name": workspace_name,
                        "count": count,
                        "status": Constants.STATUS["ACTIVE"] if count > 0 else Constants.STATUS["NO_RESOURCES"]
                    }
                return {"name": workspace_name, "count": 0, "status": Constants.STATUS["NO_RESOURCES"]}
            
            logging.warning(f"Unexpected status code {response.status_code} for workspace {workspace_name}")
            return {"name": workspace_name, "count": 0, "status": Constants.STATUS["ERROR"]}
            
        except Exception as e:
            logging.error(f"Error processing workspace {workspace_name}: {str(e)}")
            return {
                "name": workspace_name,
                "count": 0,
                "status": Constants.STATUS["ERROR"],
                "error": str(e)
            }

class SlackNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def _post_to_slack(self, payload: Dict) -> str:
        """Slackにメッセージを投稿し、レスポンスボディを返す"""
        response = requests.post(self.webhook_url, json=payload)
        response.raise_for_status()
        return response.headers.get('X-Slack-No-Retry', '')

    def send_report(self, organization: str, workspace_resources: List[Dict], total_resources: int) -> bool:
        """リソースレポートを Slack に送信"""
        try:
            now = datetime.now(Constants.JST).strftime(Constants.DATETIME_FORMAT)
            
            # リソース数が0より大きいワークスペースのみをフィルタリングしてソート
            filtered_resources = [ws for ws in workspace_resources if ws["count"] > 0]
            sorted_resources = sorted(filtered_resources, key=lambda x: x["count"], reverse=True)
            
            # メッセージを作成して送信
            message = self._create_message(organization, sorted_resources, total_resources, now)
            self._post_to_slack(message)
            return True

        except Exception as e:
            self._send_error(f"HCP Terraform リソース数の送信でエラーが発生しました: {str(e)}")
            return False

    def _create_message(self, organization: str, workspace_resources: List[Dict],
                       total_resources: int, timestamp: str) -> Dict:
        """Slackメッセージを作成"""
        # ワークスペース情報の文字列を作成
        workspace_details = ""
        for ws in workspace_resources:
            icon = Constants.STATUS_ICONS.get(ws.get("status"), Constants.STATUS_ICONS["unknown"])
            workspace_details += f"{icon} *{ws['name']}*: {ws['count']} リソース\n"

        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": ":hcp-terraform: HCP Terraform リソース数レポート"}
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Organization 名:*\n{organization}"},
                        {"type": "mrkdwn", "text": f"*課金対象リソース数:*\n{total_resources}"},
                        {"type": "mrkdwn", "text": f"*アクティブワークスペース数:*\n{len(workspace_resources)}"}
                    ]
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"実行日時: {timestamp}"}
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": workspace_details}
                }
            ]
        }

    def _send_error(self, error_message: str):
        """エラーメッセージを送信"""
        try:
            requests.post(self.webhook_url, json={"text": error_message})
        except Exception as e:
            logging.error(f"Error sending error message to Slack: {str(e)}")

def get_resource_count(slack_webhook: str = None) -> Tuple[str, int]:
    """リソース数を取得して結果を返す"""
    try:
        tf_api = TerraformAPI(
            token=os.environ["TF_TOKEN"],
            organization=os.environ["TF_ORGANIZATION"]
        )
        
        workspaces = tf_api.get_all_workspaces()
        workspace_resources = [
            tf_api.get_workspace_resources(ws["id"], ws["attributes"]["name"])
            for ws in workspaces
        ]
        
        total_resources = sum(ws["count"] for ws in workspace_resources)
        
        if slack_webhook:
            notifier = SlackNotifier(slack_webhook)
            notifier.send_report(tf_api.organization, workspace_resources, total_resources)
        
        return format_response(workspace_resources, total_resources), 200
    
    except Exception as e:
        error_message = f"エラーが発生しました: {str(e)}"
        logging.error(error_message)
        return error_message, 500

def format_response(workspace_resources: List[Dict], total_resources: int) -> str:
    """HTTP レスポンス用の文字列を生成"""
    now = datetime.now(Constants.JST).strftime(Constants.DATETIME_FORMAT)
    
    # リソース数が0より大きいワークスペースのみをフィルタリング
    filtered_resources = [ws for ws in workspace_resources if ws["count"] > 0]
    active_workspaces = len(filtered_resources)
    
    details = (f"*総リソース数: {total_resources}* "
              f"(アクティブワークスペース数: {active_workspaces})\n"
              f"実行日時: {now} (JST)\n\n"
              "ワークスペース別リソース数:\n")
    
    # ソートを適用
    sorted_resources = sorted(filtered_resources, key=lambda x: x["count"], reverse=True)
    
    for ws in sorted_resources:
        icon = Constants.STATUS_ICONS.get(ws.get("status"), Constants.STATUS_ICONS["unknown"])
        details += f"{icon} {ws['name']}: {ws['count']} リソース\n"
    
    return details

# Azure Functions のエンドポイント
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

@app.route(route="httpget", methods=["GET"])
def http_get(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP エンドポイント: リソース情報を返すのみ"""
    logging.info("Processing GET request")
    message, status_code = get_resource_count()
    return func.HttpResponse(message, status_code=status_code)

@app.route(route="httppost", methods=["POST"])
def http_post(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP エンドポイント: Slack 通知付きのリソース情報取得"""
    logging.info("Processing POST request")
    try:
        req_body = req.get_json()
        slack_webhook = req_body.get('slack_webhook')
        
        if not slack_webhook:
            return func.HttpResponse(
                "Please provide 'slack_webhook' in the request body",
                status_code=400
            )

        message, status_code = get_resource_count(slack_webhook)
        return func.HttpResponse(message, status_code=status_code)

    except ValueError:
        return func.HttpResponse(
            "Invalid JSON in request body",
            status_code=400
        )
    except Exception as e:
        error_message = f"Error occurred: {str(e)}"
        logging.error(error_message)
        return func.HttpResponse(
            error_message,
            status_code=500
        )

@app.function_name(name="timer")
@app.timer_trigger(schedule="0 0 9 * * *",
                  arg_name="timer",
                  run_on_startup=False)
def timer_trigger(timer: func.TimerRequest) -> None:
    """タイマートリガー: 環境変数 SLACK_WEBHOOK を使用して Slack に通知"""
    if timer.past_due:
        logging.info('The timer is past due!')
    
    logging.info('Timer trigger function executed at %s', 
                 datetime.now(Constants.JST).isoformat())
    
    try:
        slack_webhook = os.environ.get("SLACK_WEBHOOK")
        if slack_webhook:
            message, _ = get_resource_count(slack_webhook)
            logging.info(message)
        else:
            logging.warning("SLACK_WEBHOOK is not configured")
    except Exception as e:
        error_message = f"エラーが発生しました: {str(e)}"
        logging.error(error_message)