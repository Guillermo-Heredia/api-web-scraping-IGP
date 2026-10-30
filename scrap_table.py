import datetime
import json
import uuid
import boto3
import requests
from bs4 import BeautifulSoup


def lambda_handler(event, context):
  url = "https://ultimosismo.igp.gob.pe/productos/reportes-sismicos"

  # Encabezado para simular una petición desde navegador (el IGP bloquea scripts sin User-Agent)
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
      )
  }

  rows = []

  # 1. Solicitud HTTP a la página del IGP
  response = requests.get(url, headers=headers)
  if response.status_code == 200:
    soup = BeautifulSoup(response.content, "html.parser")
    table = soup.find("table")

    if table:
      headers_table = [header.text.strip() for header in table.find_all("th")]
      for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if cells:
          item = {}
          for i, cell in enumerate(cells):
            header_name = (
                headers_table[i]
                if i < len(headers_table)
                else f"columna_{i + 1}"
            )
            item[header_name] = cell.text.strip()
          rows.append(item)

  # 2. Respaldo (Fallback): Si el HTML no contiene la tabla por renderizado en cliente (JS)
  if not rows:
    year = datetime.datetime.now().year
    api_url = f"https://ultimosismo.igp.gob.pe/api/ultimo-sismo/ajaxb/{year}"
    api_res = requests.get(api_url, headers=headers)

    if api_res.status_code == 200:
      data = api_res.json()
      for item in data:
        rows.append({
            "Fecha": str(item.get("fechaLocal", item.get("fecha", ""))),
            "Hora": str(item.get("horaLocal", item.get("hora", ""))),
            "Magnitud": str(item.get("magnitud", "")),
            "Profundidad": str(item.get("profundidad", "")),
            "Referencia": str(item.get("referencia", "")),
            "Intensidad": str(item.get("intensidad", "")),
        })

  # 3. Limitar estrictamente a los 10 últimos sismos
  rows = rows[:10]

  if not rows:
    return {
        "statusCode": 404,
        "body": "No se encontraron reportes sísmicos en la página web",
    }

  # 4. Guardar los datos en DynamoDB
  dynamodb = boto3.resource("dynamodb")
  table = dynamodb.Table("TablaWebScrapping")

  # Eliminar todos los elementos de la tabla antes de agregar los nuevos
  scan = table.scan()
  with table.batch_writer() as batch:
    for each in scan.get("Items", []):
      batch.delete_item(Key={"id": each["id"]})

  # Insertar los 10 nuevos registros
  i = 1
  for row in rows:
    row["#"] = i
    row["id"] = str(uuid.uuid4())  # Generar un ID único para cada entrada
    table.put_item(Item=row)
    i = i + 1

  # Retornar el resultado como JSON
  return {"statusCode": 200, "body": json.dumps(rows, ensure_ascii=False)}
