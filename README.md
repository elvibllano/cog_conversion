# cog_conversion
## Come usarlo
Costruisci il docker con il comando
```
docker build -t <nome docker image> .
```
Poi fai il run del docker
```
docker run --name="<nome docker>" -d --network="bridge" -p 9003:8080 -e AWS_LAMBDA_FUNCTION_TIMEOUT="4000" --rm <nome docker image>
```
Poi da un'altra finestra di terminale richiamare il docker con la seguente richiesta curl
```
curl -XPOST "http://localhost:9003/2015-03-31/functions/function/invocations" -d '{"url": "https://sinergia-techfem.s3.eu-central-1.amazonaws.com/cantieri/cantiere-1/volo-6-2021-12-16/DSM.gtif"}'
```
Il link nella richiesta curl è un DSM di prova per controllare se la conversione avviene correttamente
