import json
import logging
from concurrent.futures import ThreadPoolExecutor
import urllib.request

logger = logging.getLogger(__name__)


def send_telegram_alert(bot_token: str, chat_id: str, message: str) -> bool:
  """Envía una alerta remota por Telegram utilizando la biblioteca estándar de Python."""
  if not bot_token or not chat_id:
    return False

  url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
  payload = json.dumps({"chat_id": chat_id, "text": message}).encode("utf-8")
  request = urllib.request.Request(
    url,
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
  )

  try:
    with urllib.request.urlopen(request, timeout=5) as response:
      if response.status == 200:
        logger.info("Notificación de Telegram enviada.")
        return True
      logger.error("Telegram devolvió HTTP %s.", response.status)
  except Exception as exc:
    logger.error("No se pudo enviar la notificación de Telegram (%s).", type(exc).__name__)
  return False


class TelegramNotifier:
  def __init__(self, bot_token: str, chat_id: str, enabled: bool = True):
    self.bot_token = bot_token
    self.chat_id = chat_id
    self.enabled = enabled
    self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="telegram")

  def send_alert(self, message: str) -> bool:
    """Encola una alerta para enviarla sin bloquear al recolector."""
    if not self.enabled:
      return False
    if not self.bot_token or not self.chat_id:
      logger.warning("Telegram está habilitado pero faltan credenciales.")
      return False
    try:
      self._executor.submit(send_telegram_alert, self.bot_token, self.chat_id, message)
    except RuntimeError:
      logger.warning("No se pudo encolar la notificación de Telegram.")
      return False
    return True

  def close(self):
    self._executor.shutdown(wait=True, cancel_futures=True)