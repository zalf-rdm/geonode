# Configuração final — Keycloak / ORCID — 2026-10-01

Ambiente de teste: https://identity-e.dataservice.zalf.de/, realm `ORCID`. “Broker” é o papel do Keycloak como intermediário entre as aplicações e o ORCID Sandbox. O provedor configurado é `orcid`; `lte-orcid` foi preservado.

## Configurações necessárias

| Local | Campo | Valor |
| --- | --- | --- |
| Ambos os clients / Capability config | Client authentication / Standard flow | On / On |
| Ambos os clients / Capability config | Require PKCE / Code challenge method | On / S256 |
| Ambos os clients / Access settings | Valid redirect URIs | Callbacks HTTPS existentes de cada aplicativo, incluindo idioma e prefixo `/upload/` no Upload Tool |
| Ambos os clients / Access settings | Valid post logout redirect URIs | `https://repository-e.dataservice.zalf.de/` |
| Ambos os clients / Logout settings | Front channel logout | Off |
| Ambos os clients / Logout settings | Backchannel logout session required | On |
| GeoNode / Logout settings | Backchannel logout URL | `https://repository-e.dataservice.zalf.de/sso/backchannel-logout/` |
| Upload Tool / Logout settings | Backchannel logout URL | `https://repository-e.dataservice.zalf.de/upload/sso/backchannel-logout/` |
| Ambos os clients / Advanced | ID Token Signature Algorithm | RS256 |
| Ambos os clients / Compatibility Modes | Use refresh tokens | On |
| Identity providers / orcid / Advanced | Scopes | `openid` |
| Identity providers / orcid / Advanced | Accepts prompt=none forward from client | Off |
| Identity providers / orcid / API | `config.prompt` | `login` |

Clients existentes: GeoNode `repository-e.dataservice.zalf.de`; Upload Tool `upload-e.dataservice.zalf.de`. Os callbacks e os vínculos de identidade existentes foram preservados. Os outros campos presentes nos prints são contexto e não uma recomendação para alterá-los.

## Prints anotados

Os arquivos `keycloak-geonode-01` até `05` e `keycloak-upload-tool-01` até `05` mostram as cinco seções dos clients. Os retângulos vermelhos identificam os controles necessários. `keycloak-orcid-06-scope-openid.png` mostra o provedor externo.

O plugin `keycloak-orcid-1.5.0` não apresenta `prompt` como campo na interface administrativa. Esse valor foi salvo pela Admin REST API e consta em `identity-provider-orcid.json`; não há um print fictício desse campo. Para aplicar o mesmo ajuste, autentique o `kcadm.sh` no servidor correto e use:

```sh
kcadm.sh update identity-provider/instances/orcid -r ORCID \
  -s config.defaultScope=openid \
  -s config.prompt=login \
  -s config.acceptsPromptNoneForwardFromClient=false
```

Leia a configuração atual antes e depois de alterar; mantenha o client ID, o secret e os mappers existentes. Não substitua o provedor pelo JSON sanitizado.

A [documentação oficial de ORCID OpenID Connect](https://github.com/ORCID/ORCID-Source/blob/main/orcid-web/ORCID_AUTH_WITH_OPENID_CONNECT.md) exige `openid` para processar `prompt`: substituir `/authenticate` por `openid` é essencial. Apenas `prompt=login` com `/authenticate` foi testado e continuou permitindo login automático.

## JSON

`realm-ORCID.json`, `client-geonode.json`, `client-upload-tool.json` e `identity-provider-orcid.json` são representações obtidas da Admin API após as alterações. Segredos, senhas e tokens foram removidos. O arquivo do realm contém suas configurações, não um backup completo de usuários, roles, flows, mappers e credenciais. Estes arquivos documentam o estado observado; não são um pacote de restauração completo.

## Comportamento esperado

1. Login no Upload → catálogo: a página HTML do catálogo consulta silenciosamente a sessão Keycloak (`prompt=none`), cria a sessão GeoNode e preserva o destino. Não pede novas credenciais enquanto a sessão central estiver ativa.
2. O botão Logout do dropdown de perfil envia POST com CSRF, revoga a sessão local e encerra a sessão Keycloak. O backchannel revoga as sessões correspondentes na outra aplicação.
3. Depois do logout, a página inicial permite navegação anônima. Clicar Upload inicia novo login e o ORCID pede credenciais mesmo que o navegador ainda tenha cookies ORCID.
4. Logout iniciado no Keycloak invalida os dois aplicativos. Uma sessão independente em outro navegador permanece ativa.

O logout não apaga os cookies externos ORCID; a nova autenticação obrigatória é garantida por `openid` + `prompt=login` quando não existe uma sessão Keycloak válida.

## Aplicação e entrega

A integração e as migrações foram aplicadas ao pod GeoNode e aos dois pods web Upload Tool para validação, por autorização do usuário. As configurações Keycloak são persistentes. A cópia do código nos containers é temporária e precisa ser incorporada às imagens e ao release normal; um restart pode removê-la.

Os runbooks completos ficam em `repository_sso/README.md` no GeoNode e `src/repository_sso/README.md` no Upload Tool. Os JSON não contêm os secrets necessários às aplicações.

## Evidências de validação

- 31 testes Django por aplicação (62 execuções): JWT, replay, isolamento, CSRF, logout, refresh, vínculos existentes, health probe e handoff do catálogo.
- Em 2026-10-01, Chromium com navegador limpo: login iniciado em `/upload/wizard/overview/` → `/catalogue/#/` → página inicial autenticada, em 1440 e 390 px. O navegador não possuía cookie GeoNode antes de abrir o catálogo.
- Logout pelo menu de cada aplicativo e revogação pelo Keycloak foram testados com ORCID Sandbox real. Sessões antigas e cookies reapresentados não restauraram acesso; uma sessão independente permaneceu ativa.
- Menu responsivo: 320/360/375/390/412/430/768/1440 px; botão Logout ≥44 px e sem overflow horizontal.
- Build de produção MapStore passou com cinco avisos (diretórios opcionais de tradução/configuração/Cesium e limites de tamanho dos bundles). A correção do menu está no componente ZALF de origem; não houve edição manual de bundles compilados.

Repetição: `ORCID_QA_ENV=/caminho/para/.env node repository_sso/tests/live_catalogue.cjs` e `node repository_sso/tests/live_reauth.cjs` com o mesmo ambiente. Requer Playwright/Chromium e credenciais Sandbox, lidas sem impressão. `REPOSITORY_QA_URL` permite configurar a URL de teste. `MAPSTORE_QA_DIST` permite validar os assets recém-compilados no navegador antes de implantá-los; registre explicitamente quando essa opção for usada. A revogação administrativa requer o helper privado indicado por `ORCID_QA_PROVIDER_HELPER` e é restrita à sessão QA.

As suítes completas das aplicações e refresh verdadeiramente simultâneo em PostgreSQL não foram executados. Não marcar essas verificações como concluídas.

### Retomada em 2026-10-02

A API Kubernetes `10.14.10.140:6443` estava inacessível após interrupção da conexão do usuário. A cópia dos novos assets MapStore para o cluster ficou pendente até a reconexão da VPN/rede ZALF. A nova tentativa de teste público encontrou timeouts de navegação; isso não substitui os resultados concluídos em 2026-10-01.

As PRs estão abertas e coordenadas: [GeoNode #780](https://github.com/zalf-rdm/geonode/pull/780), [Upload Tool #554](https://github.com/zalf-rdm/upload-tool/pull/554), [MapStore #151](https://github.com/zalf-rdm/geonode-mapstore-client/pull/151). As issues #778/#553 têm os passos comprovados marcados e os passos de release pendentes separados.

Na retomada, o teste de logout pelo menu com os assets compilados servidos somente ao navegador passou para Upload e GeoNode em desktop (1440 px): SSO, credenciais obrigatórias na reentrada, abas antigas do Upload/GeoNode/catálogo anônimas e replay do cookie antigo rejeitado; zero erros JavaScript. Isso valida a compilação, mas não substitui a implantação dos assets no cluster. A validação Flake8/Black do GeoNode passou no CI após correção de formatação.

O teste mobile encontrou o mesmo `/upload` no rodapé React, além da navbar. Os dois componentes ZALF foram corrigidos para `/upload/`. O teste agora abre o menu e seleciona explicitamente a navbar, e verifica separadamente o href do rodapé, evitando confundir um link visível no rodapé com um item do menu fechado. A implantação dos assets corrigidos permanece pendente.
