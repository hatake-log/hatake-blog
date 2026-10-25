---
title: "Codablecashのソースコードで、ノードが「仲間」を見つける仕組みを追いかけてみる"
slug: "p2p-discovery"
date: 2026-10-17T09:00:00+09:00
draft: true
tags: ["暗号資産", "Codablecash"]
# cover:
#   image: "images/p2p-discovery-top.png"
#   alt: "Codablecashのノードが仲間を見つける仕組み"
---

<!-- 下書きメモ(公開時に削除)
- 公開時: ファイル名を次の連番(17-p2p-discovery.md)に、dateを現在時刻より前に、draft: falseに
- カバー画像は未作成(緑キャラ路線で「電話帳を見ながら電話をかけるノード」あたり)
- 本文中の開発者ツイートはdev-statements.md 2026-10-12採録のもの。ツイートIDは未採録なのでアカウントへのリンクのみ
- 触れないと決めたこと: 接続IDの作り方、ArrayNetworkSheeder::getNumZonesの中身、台帳の寿命・IPv4/IPv6の扱い、
  掘れたブロックの配り方(MinerMinedReportCommandMessageの同一ゾーン一斉送信。2026-10-24に削除:
  開発者が10/19→10/24で「ブロックを流す役目」を投票ノード側へ移す設計変更を公言したため、967b7ebの描写は公開版と食い違う公算)
  (開発者が見直し中と公言している領域なので、仕組みの骨格だけ書く)
-->

[前回](/posts/ticket-lock-period/)・[前々回](/posts/staking-in-code/)はステーキングのコードを読みました。今回は少し場所を変えて、**ネットワーク**のほうを見てみます。

テーマは「ノードを起動したとき、ほかのノードをどうやって見つけて、つながるのか」です。

きっかけは、開発者さんの2026年10月のこの投稿でした。

> [Codablecash進捗]
> P2PネットワークのDNS部分を見直しています。
> ここがしっかり出来ると、安定系に突入でき、テストネットがスムーズにたちがあります。
>
> —— [@iizuka](https://x.com/iizuka)（2026年10月12日ごろの投稿）

「DNS」と聞くと、ドメイン名からIPアドレスを調べるインターネットのあれを思い浮かべますが、コードを読んでみると、ここでいうDNSは**各ノードが持っている「ほかのノードの連絡先の台帳」**のことでした。見直し中、ということは今のコードは変わる前提です。だからこそ、変わる前の形を一度ちゃんと読んでおけば、公開版が出たときに「何が変わったのか」が分かるはず、というのが今回の動機です。

記事内のコード引用は、Codablecashのソースコード[`967b7eb`](https://github.com/alinous-core/codablecash/tree/967b7eb4fc41c568a2c2b05cc63018b51e0d3fa5)（2026年9月8日）のコミットからお借りしています。

{{< tips >}}
Codablecashは開発中のプロジェクトで、今回の部分はとくに開発者さんが「見直している」と明言している箇所です。ここに出てくる数値や手順は公開版で変わっている可能性が高いので、「どういう考え方で仲間を見つけているのか」の骨格を読む、くらいの気持ちでお付き合いください。

また、前回までと同じく、私はPHPを少し触るくらいでC++の知識はありません。クラス名と短いコードを眺めて「ふーむ」と言う回です。
{{< /tips >}}

## 「仲間を見つける」とは

暗号資産（仮想通貨）のネットワークには、中心になるサーバーがありません。

参加しているノード（ソフトを動かしているコンピュータ）が互いにつながって、新しいブロックやトランザクションについて「ねぇねぇ、こんなのが来たよ」と回し合っています。これがP2P（ピア・ツー・ピア）です。

ここで気になるのが、今回のテーマでもある**いちばん最初、誰ともつながっていないノードは、相手をどうやって知るのか。**という部分です。

Bitcoinの場合は、開発者がソフトの中にいくつかの「とりあえずここに聞け」という宛先（シード）を埋め込んでいて、起動したノードはそこに聞いて他のノードの一覧を手に入れます。このあたりは[Binary Igorさんの記事](https://binaryigor.com/bitcoin-p2p-network.html)がとても丁寧で、今回の記事もかなり影響を受けています。

では、Codablecashはどうなっているのか見てみましょう。

{{< tips title="先に「ゾーン」の説明" color="sky" >}}
Codablecashのコードにはいたるところに`zone`という言葉が出てきます。これはネットワークを複数の区画に分けて並行して動かす設計（いわゆるシャーディング）の区画のことです。ノードは起動時に自分の所属ゾーンを1つ持ち、他のゾーンとも少しだけつながります。

今回の記事では「自分のゾーン」と「ほかのゾーン」で接続の数が違う、というところにだけ関わってきます。最初のテストネットがいくつのゾーンで始まるかは、この記事を書いている時点では分かりません。
{{< /tips >}}

## 全体の流れ

ノードが起動してから仲間とつながるまでを、コードベースで追ったところ、おおまかに以下のような順番でした。

1. **自分の名札を用意する**: ノードの識別子（`NodeIdentifier`）は、ランダムな番号ではなく**公開鍵**
2. **待ち受けを始める**: `P2pServer`が自分のポートで他ノードからの接続を待つ
3. **最初の相手を「シーダー」から知る**: `INetworkSeeder`が渡す数件の連絡先（`P2pNodeRecord`）が出発点
4. **最初の相手から「電話帳」をもらう**: 相手ノードの台帳（`P2pDnsManager`）をゾーンごとに最大256件ダウンロードして、自分の台帳に書き込む
5. **電話帳から選んでつなぐ**: 自分のゾーンは8本、ほかのゾーンは4本になるまで、台帳からランダムに選んで接続する（`ConnectNodeSelector`）
6. **つないだら名乗る、名乗られた側は折り返して確かめる**: ログイン（`LoginPubSubCommand`）に自分の連絡先を添えて送る。受けた側は**その連絡先に自分から接続し直して、届いたときだけ**台帳に登録する（`DnsCheckCommandMessage`）
7. **つながったあと**: 3ノードを選んでブロックを同期し、以後は掘れたブロックをゾーン内に回す
8. **退出するとき**: 「やめます」の通知（`NodeShutdownCommand`）を全ゾーンに回し、受け取ったノードは台帳から消す

1から順に見てゆきます。

## 関連するクラス

今回の登場人物は、`src_blockchain_p2p/`配下と、`src_blockchain/bc_network_instance/`配下に分かれていました。

- `NodeIdentifier` — ノードの名札（中身は公開鍵）
- `P2pNodeRecord` — 連絡先1件。ゾーン・名札・ホスト・ポート・プロトコルなど
- `INetworkSeeder` / `ArrayNetworkSheeder` — 最初の連絡先を渡す「シーダー」（綴りは上流のまま）
- `P2pDnsManager` / `P2pNodeDatabase` — 連絡先の台帳。今回の「DNS」の正体
- `DownloadDnsInfoCommand` — 相手の台帳をもらう命令
- `ConnectNodeSelector` — 台帳から接続先をランダムに選ぶ
- `LoginPubSubCommand` / `NodeNetworkInfo` — ログインと、そのとき添える自分の連絡先
- `DnsCheckCommandMessage` — 名乗られた連絡先に折り返して確かめる
- `NodeShutdownCommand` — 退出の通知

## 1. ノードの名札は公開鍵

まず、ノードを区別する`NodeIdentifier`です。

```cpp
// src_blockchain/bc_network/NodeIdentifier.h
class NodeIdentifier : public IBlockObject {
public:
	// ・・・・・
	const BigInteger* getPublicKey() const noexcept {
		return this->nodeIdentifier;
	}
	// ・・・・・
private:
	BigInteger* nodeIdentifier; // pubkey
};
```

メンバ変数の名前は`nodeIdentifier`ですが、コメントに`pubkey`とある通り、中身は**公開鍵そのもの**です。対になる秘密鍵は`NodeIdentifierSource`が持っていて、ノードはこの鍵でログインや各種の通知に署名します。

つまりCodablecashのノードIDは、「好きに付けられる名札」ではなく「本人しか作れない署名ができる名札」です。[前々回の記事](/posts/staking-in-code/)で出てきた、投票プールを登録するときの`NodeIdentifier`と同じものです。P2Pの名札と、ステーキングでチケットを預ける先の指名が、同じ鍵で行われているのですね。

## 2〜3. 待ち受けと、最初の相手（シーダー）

ノードの起動は`CodablecashNetworkNode::startNetwork()`から始まります。ここに今回の流れがほぼ全部並んでいました。

```cpp
// src_blockchain/bc_network_instance/CodablecashNetworkNode.cpp
void CodablecashNetworkNode::startNetwork(INetworkSeeder* seeder, bool pending) {
	// ・・・・・
	// startNetwork
	const UnicodeString* host = this->nwconfig->getHost();
	int port = this->nwconfig->getPort();

	this->inst->startNetwork(host, port);          // 待ち受けを始める

	// start processors
	// ・・・・・

	// init database
	if(seeder != nullptr){
		ArrayList<P2pNodeRecord>* seedList = seeder->getSeedNodes(); __STP(seedList);
		// ・・・・・
		if(seedList != nullptr && !seedList->isEmpty()){
			initDatabase(seedList);                  // シーダーの連絡先から台帳を作る
		}
	}

	// init connections
	maintainNetwork();                               // 台帳から選んで接続する
}
```

引数で渡されている`INetworkSeeder`が「最初の相手」を知る手段です。中身はとてもシンプルで、連絡先（`P2pNodeRecord`）を配列で持っているだけでした。

```cpp
// src_blockchain/bc_network_instance/INetworkSeeder.h
class INetworkSeeder {
public:
	// ・・・・・
	virtual ArrayList<P2pNodeRecord>* getSeedNodes() const noexcept = 0;
	virtual void addRecord(const P2pNodeRecord* record) noexcept = 0;
	// ・・・・・
};
```

連絡先1件の`P2pNodeRecord`には、以下のようなものが入っています。

| 項目 | 中身 |
|---|---|
| `zone` | その相手のゾーン番号 |
| `nodeId` | 相手の名札（公開鍵） |
| `canonicalName` | 人間向けの名前（テストでは`node_01`のような文字列） |
| `protocol` | `TCP_IP_V4`か`TCP_IP_V6`か |
| `host` / `port` | 接続先のアドレスとポート |
| `createdTime` / `lastUpdatedTime` | 登録・更新の時刻 |
| `list` | この相手がどのノードとつながっているか |

Bitcoinではシードの宛先がソフトに埋め込まれていますが、Codablecashの967b7ebの時点では、**シーダーに何を入れるかは呼び出し側に任されています**。実際の使い方は、上流のテストコードがいちばん分かりやすい説明書になっていました。

```cpp
// src_test/blockchain/testnet/test_first_net.cpp
ArrayNetworkSheeder seeder;
CodablecashNetworkNode node01(dirNode01, config01, &logger);
{
	// First
	node01.setNodeName(L"node01");
	node01.generateNetwork(0, 1); // zone 0
	node01.startNetwork(&seeder, false);        // 1台目: シーダーは空のまま起動
	// ・・・・・
	{
		uint16_t zone = 0;
		NodeIdentifier nodeId = source->toNodeIdentifier();
		const wchar_t* host = L"::1";
		int port = config01->getPort();
		const UnicodeString* cname = config01->getCanonicalName();
		P2pNodeRecord* rec = P2pNodeRecord::createIpV6Record(zone, &nodeId, cname, host, port); __STP(rec);
		seeder.addRecord(rec);                  // 1台目の連絡先をシーダーに入れる
	}
}
// ・・・・・
CodablecashNetworkNode node02(dirNode02, config02, &logger);
{
	// second
	node02.initBlank(0, 1); // zone 0
	// ・・・・・
	node02.setNodeName(L"node02");
	node02.startNetwork(&seeder, true);         // 2台目: 1台目の連絡先が入ったシーダーで起動
	node02.syncNetwork();
	// ・・・・・
}
```

1台目は誰も知らないまま起動して（最初のノードなので当然ですね）、その連絡先をシーダーに足してから2台目を起動する、という手順です。この「1台目」の役が、テストネットでいう開発者さんのシードノードになるのだと思います。

## 4. 最初の相手から「電話帳」をもらう

シーダーから連絡先を受け取ったノードは、`initDatabase()`→`P2pDnsManager::importSeeds()`で、その相手に接続して**相手が持っている台帳**をもらいに行きます。

```cpp
// src_blockchain_p2p/bc_p2p_info/P2pDnsManager.cpp
void P2pDnsManager::importSeeds(int numZone, const P2pNodeRecord *nodeRecord, ISystemLogger *logger) {
	// ・・・・・
	const UnicodeString* host = nodeRecord->getHost();
	int port = nodeRecord->getPort();

	try{
		for(int i = 0; i != numZone; ++i){
			doImportSeeds(i, host, port, logger);     // ゾーンごとに台帳をもらう
		}

		// add seed
		this->database->importUnconnectedNode(nodeRecord);   // シード自身も台帳に入れる
	}
	// ・・・・・
}

void P2pDnsManager::doImportSeeds(uint16_t zone, const UnicodeString *host, int port, ISystemLogger *logger) {
	P2pClient client(zone, logger);
	// ・・・・・（接続）

	DownloadDnsInfoCommand command(zone);
	client.sign(&command);
	AbstractCommandResponse* response = client.sendCommnad(&command); __STP(response);

	// client close
	client.close();

	DownloadDnsInfoCommandResponse* dnsInfoResponse = dynamic_cast<DownloadDnsInfoCommandResponse*>(response);
	if(dnsInfoResponse != nullptr){
		const ArrayList<P2pNodeRecord>* list = dnsInfoResponse->getRecords();
		// ・・・・・
		for(int i = 0; i != maxLoop; ++i){
			P2pNodeRecord* rec = list->get(i);
			this->database->importUnconnectedNode(rec);   // もらった連絡先を自分の台帳へ
		}
	}
}
```

ここで面白かったのが、台帳をもらうときに使っている`P2pClient`です。これは**ノード同士の接続ではなく、ウォレットがノードに接続するときと同じ「お客さん」用の接続**でした（ログインの命令が`LoginClientCommand`で、ノード同士の`LoginPubSubCommand`とは別物）。

つまり、まだ誰ともつながっていないノードは、いきなり「仲間です」と名乗るのではなく、まずお客さんとして「ほかにどんなノードがいますか？」と聞いて、電話帳だけもらって帰る、という手順になっています。

もらえる件数には上限があって、1回の`DownloadDnsInfoCommand`で**最大256件**でした。

```cpp
// src_blockchain_p2p/bc_p2p_cmd_client/DownloadDnsInfoCommand.cpp
DownloadDnsInfoCommand::DownloadDnsInfoCommand(uint16_t zone) : AbstractClientRequestCommand(TYPE_CLIENT_DOWNLOAD_DNS) {
	this->zone = zone;
	this->maxNum = 256;
}
```

受けた側（台帳を渡す側）は、自分の`P2pDnsManager`から該当ゾーンの連絡先を取り出して返しているだけです。

```cpp
// src_blockchain_p2p/bc_p2p_cmd_client/DownloadDnsInfoCommand.cpp
AbstractCommandResponse* DownloadDnsInfoCommand::executeAsClient(ClientNodeHandshake *clientHandshake, CodablecashNodeInstance *inst) const {
	P2pDnsManager* p2pManager = inst->getP2pDnsManager();
	DownloadDnsInfoCommandResponse* respose = new DownloadDnsInfoCommandResponse(); __STP(respose);

	ArrayList<P2pNodeRecord>* list = p2pManager->getZoneRecords(this->zone, this->maxNum); __STP(list);
	// ・・・・・
	respose->importRecords(list);

	return __STP_MV(respose);
}
```

ちなみに、この台帳はメモリ上ではなく、ノードのデータフォルダの中にB木（`P2pNodeDatabase`）として保存されています。一度もらった電話帳は再起動しても手元に残る、ということですね。

## 5. 電話帳から選んでつなぐ

台帳ができたら、いよいよ仲間に接続します。`maintainNetwork()`がゾーンごとに「あと何本足りないか」を数えて、足りないぶんだけ台帳から選んでつなぎます。

```cpp
// src_blockchain/bc/CodablecashNodeInstance.cpp
void CodablecashNodeInstance::__maintainNetwork(uint16_t zone) {
	int numNeedConnection = this->param->getNumConnectionExtShard();   // ほかのゾーン: 4
	if(zone == getZoneSelf()){
		numNeedConnection = this->param->getNumConnectionOwnShard();   // 自分のゾーン: 8
	}

	int currentSize = this->p2pManager->getNumNodes(zone);   // 今つながっている数
	int diff = numNeedConnection - currentSize;               // 足りない数

	if(diff > 0){
		ArrayList<P2pNodeRecord>* list = this->p2pDnsManager->getZoneRecords(zone, 1024); __STP(list);
		// ・・・・・
		ConnectNodeSelector selector;
		selector.importCandidates(list);          // 台帳の連絡先を候補にする

		while(diff > 0 && selector.hasNext()){
			const P2pNodeRecord* rec = selector.fetchNext();   // 1件選ぶ

			if(__connectWithP2pNodeRecord(rec)){  // つながったら
				diff--;                           // 残りを減らす
			}
		}
	}
}
```

本数の既定値は、ステーキングの記事でも何度も出てきた`CodablecashSystemParam`にありました。

```cpp
// src_blockchain/bc/CodablecashSystemParam.cpp
CodablecashSystemParam::CodablecashSystemParam() {
	// ・・・・・
	this->numConnectionOwnShard = 8;
	this->numConnectionExtShard = 4;

	this->numInitialSyncNodes = 3;
	// ・・・・・
}
```

**自分のゾーンに8本、ほかの各ゾーンに4本**。ブロックの伝播が大事なのは自分のゾーンなので、そちらを厚くしているのだと思います。

接続に失敗した相手（`__connectWithP2pNodeRecord()`が`false`）はカウントされず、次の候補に進みます。候補の選び方は`ConnectNodeSelector`で、候補を読み込んだ時点の時刻をSHA-256にかけて大きな数を1つ作り、それを「残っている候補の数」で割った余りを添字にして1件ずつ取り出していました。取り出した候補は候補から外れるので、同じ相手が二度選ばれることはありません。

```cpp
// src_blockchain_p2p/bc_p2p_selector/ConnectNodeSelector.cpp
const P2pNodeRecord* ConnectNodeSelector::fetchNext() const {
	int index = toIndex(this->candidates->size());     // 候補の数で割った余りを添字に
	P2pNodeRecord* record = this->candidates->remove(index);   // 取り出した候補は候補から外す
	this->usedCandidates->addElement(record);
	return record;
}
```

台帳の上から順に、ではなくランダムに選ぶのは、みんなが同じ数件に集中しないための工夫でしょうか。Bitcoinでも接続先はランダムに選びますし、このあたりは定番の考え方のようです。

## 6. つないだら名乗る、名乗られた側は折り返して確かめる

ここが今回いちばん「なるほど」と思った部分です。

### つなぐ側: ログインに自分の連絡先を添える

相手に接続したノードは、`loginNode()`でログインの命令（`LoginPubSubCommand`）を送ります。このとき**自分の連絡先（`NodeNetworkInfo`）を添えて、署名**しています。

```cpp
// src_blockchain/bc/CodablecashNodeInstance.cpp
void CodablecashNodeInstance::loginNode(uint16_t zone, P2pHandshake *handshake, const UnicodeString* canonicalName) {
	// login
	NodeIdentifierSource* source = this->p2pRequestProcessor->getNetworkKey();   // 自分の鍵

	uint16_t zoneSelf = this->statusCache->getZoneSelf();
	LoginPubSubCommand cmd(zoneSelf, canonicalName);

	{
		NodeIdentifier nodeId = source->toNodeIdentifier();   // 鍵から名札を作る
		SystemTimestamp tm;

		int protocol = this->p2pManager->getProtocol();
		const UnicodeString* host = this->p2pManager->getHost();
		uint32_t port = this->p2pManager->getPort();

		NodeNetworkInfo info(zoneSelf, &nodeId, &tm, protocol, host, port);   // 「私の連絡先はここです」
		info.setCanonicalName(this->nodeName);

		cmd.setNodeNetworkInfo(&info);
	}

	cmd.sign(source);   // 自分の鍵で署名

	AbstractCommandResponse* response = handshake->publishCommand(&cmd); __STP(response);
	// ・・・・・
	uint32_t type = response->getType();
	if(type != AbstractCommandResponse::TYPE_RES_OK){
		throw new P2pHandshakeAuthenticationException(L"Already connected.", __FILE__, __LINE__);
	}
}
```

最後の部分で、相手から`OK`以外が返ってきたら「もうつながっている」として例外を投げています。これは次の受ける側のコードと対になっています。

### 受ける側: 署名を確かめ、折り返して確かめ、それから台帳へ

ログインを受けたノード側の処理が`LoginPubSubCommand::execute()`です。

```cpp
// src_blockchain_p2p/bc_p2p_cmd/LoginPubSubCommand.cpp
AbstractCommandResponse* LoginPubSubCommand::execute(const PubSubId* pubsubId, IPubsubCommandListner *listner) const {
	try{
		checkSignature();                      // 1. 署名が名札（公開鍵）と合うか
	}
	catch(Exception* e){
		delete e;
		return new SignatureErrorResponse();
	}

	{
		// ・・・・・
		BlockchainNodeHandshake* node = p2pMgr->getNodeHandshakeByNodeId(this->nodeId);
		StackHandshakeReleaser __releaser(node);
		if(node != nullptr){                   // 2. 同じ名札がもうつながっていたら断る
			ErrorPubsubResponse* res = new ErrorPubsubResponse();
			return res;
		}
	}

	listner->fireExecuteCommand(pubsubId, this);   // 3. 接続として登録

	// check & register dns
	if(this->nodeNetInfo){                     // 4. 連絡先が添えられていたら、確認を依頼
		// ・・・・・
		netDnsProcessor->requestDnsCheck(this->nodeNetInfo);
	}

	OkPubsubResponse* res = new OkPubsubResponse();
	return res;
}
```

順番に、

1. **署名の確認**。名札は公開鍵なので、「その名札の持ち主しか作れない署名か」を確かめられます。名札のなりすましはここで弾かれます
2. **同じ名札が二重につながることの拒否**。同じ鍵のノードを2台立てても、同じ相手には1本しかつなげません
3. 接続の登録
4. 添えられていた連絡先を、**そのまま台帳に入れるのではなく、確認に回す**

4の「確認」が`DnsCheckCommandMessage`です。

```cpp
// src_blockchain_p2p/bc_p2p_processor/DnsCheckCommandMessage.cpp
void DnsCheckCommandMessage::checkAndRegister(P2pRequestProcessor* processor, ISystemLogger* logger) {
	{
		IClientSocket* con = this->nodeNetInfo->getConnection(); __STP(con);   // 申告された連絡先に自分から接続してみる
		StackConnectionCloser _st_closer(con);

		ExceptionThrower<PubsubNetworkException>::throwExceptionIfCondition(!con->isConnected(), L"Connection does not reach.", __FILE__, __LINE__);
	}

	// dns check
	P2pDnsManager* dnsManager = processor->getP2pDnsManager();
	dnsManager->updateOrAddRecord(this->nodeNetInfo, logger);   // 届いたときだけ台帳に登録
}
```

「私の連絡先はここです」と言われたら、**その連絡先に自分からつなぎ直してみて、本当に届いたときだけ台帳に書く**。届かなければ例外になって、台帳には載りません。

これ、地味ですがとても大事なことを決めています。

{{< tips title="待ち受けしていないノードは、電話帳に載らない" color="sky" >}}
自宅のルーターの内側でノードを動かして、外からの接続（待ち受け）を開けていない場合、申告した連絡先に相手が折り返してもつながりません。すると、そのノードは**相手の台帳に登録されず、電話帳が他のノードに配られても自分は載っていない**ことになります。

一方で、自分から外に向けてつなぐことはできるので、仲間から情報をもらうこと自体はできます。「電話帳に載る公開ノード」と「載らない非公開ノード」の違いは、この折り返し確認で決まっているようです。
{{< /tips >}}

## 7. つながったあと

無事に仲間とつながったあとは、まず**追いつく**ことからです。テストコードで`startNetwork()`の直後に呼ばれていた`syncNetwork()`は、ゾーンごとに「つながっているノードから`numInitialSyncNodes`（3）台をランダムに選び、それぞれにブロックヘッダをもらいに行く」という動きでした。

```cpp
// src_blockchain/bc_network_instance_sync/AbstractZoneSync.cpp
ArrayList<NodeIdentifier>* nodelist = p2pManager->getNodeIds(this->zone); __STP(nodelist);
// ・・・・・
int num = param->getNumInitialSyncNodes();     // 3
RamdomNodesSelector sel(nodelist, num);          // つながっている中から3台

while(sel.hasNext()){
	const NodeIdentifier* nodeId = sel.next();
	// ・・・・・
	HeaderSyncWorker* worker = new HeaderSyncWorker(this->zone, nodeId, this, this->logger, &str);
	this->workers->addElement(worker);
	worker->start();
}
```

仲間に追いついたら、あとは同じ高さで新しいブロックやトランザクションを受け取る日常です。そのブロックを「誰がどう配るか」は、開発者さんが見直すと公言している部分なので、今回は踏み込まずにおきます。

## 8. 退出するとき

最後に、ノードをきれいに止めるときの話です。終了するノードは`NodeShutdownCommand`に自分の名札と時刻を署名して付け、全ゾーンに流します。受け取ったノードの処理がこちら。

```cpp
// src_blockchain_p2p/bc_p2p_cmd_network/NodeShutdownCommand.cpp
AbstractCommandResponse* NodeShutdownCommand::executeAsNode(BlockchainNodeHandshake *nodeHandShake, CodablecashNodeInstance *inst, bool suspend) const {
	{
		bool vl = verifyTimestamp();   // 本人の署名か
		// ・・・・・
	}

	bool updated = updateShutdownNode(inst);   // 台帳から消して、接続を切る

	if(!suspend && updated && this->hops < 5){   // まだ5回転送されていなければ
		// ・・・・・
		command.incHpos();
		command.sign(source);
		// ・・・・・
		p2pManager->broadCastAllZones(this->nodeId, &command, processor);   // 自分の仲間にも転送
	}

	return new OkPubsubResponse();
}
```

「やめます」を受け取ったら、台帳から消して接続を切り、自分の仲間にも転送する。転送は`hops`で数えていて、5回までです。噂が無限に回り続けないようにする、よくある工夫ですね。

ここでも署名を確かめているので、他人が「あのノードはやめました」と嘘の通知を流しても、台帳から消されることはありません。名札が公開鍵になっていることが、いろいろな場面で効いています。

## ざっくりまとめ

| 段階 | やること | 数字（967b7eb時点） |
|---|---|---|
| 名札 | 公開鍵をノードIDにする | — |
| 最初の相手 | シーダー（`INetworkSeeder`）に入っている連絡先 | 呼び出し側が指定 |
| 電話帳 | 最初の相手から台帳をもらう | ゾーンごとに最大256件 |
| 接続 | 台帳からランダムに選んでつなぐ | 自分のゾーン8本、ほかのゾーン4本 |
| 名乗り | ログインに連絡先を添えて署名。受けた側は折り返して確認 | 届かなければ台帳に載らない |
| 追いつき | 仲間から3台選んでヘッダをもらう | 3台 |
| 退出 | 署名つきの通知を全ゾーンへ。転送は5回まで | 5ホップ |

読んでみて思ったのは、「どうやって見つけるか」の答えは意外とシンプルで、**最初の1件だけは人間が教える。あとは電話帳を交換して、ランダムに選んでつなぐ**、ということでした。Bitcoinとの大きな違いは、その「最初の1件」をソフトに埋め込んでいるか、起動時に渡しているか、という点で、Codablecashの967b7ebの時点では後者です。公開版で「開発者さんのシードノードをどう指定するのか」が、テストネットに参加するときの最初のハードルになりそうです。

冒頭の開発者さんの投稿にあった「DNS部分の見直し」は、まさにこの電話帳（`P2pDnsManager`）まわりの話だと思います。今回読んだ「もらう・確認して載せる・退出で消す」のうち、どこが変わるのか。公開版が出たらこの記事と見比べてみるつもりです。

<!-- 公開版で確かめたいこと(記事には載せない作業メモ)
- シードノードの指定方法(設定ファイル/CLI)。チェックリスト14
- 所属ゾーンの指定方法と初期ゾーン構成。チェックリスト16
- 自ノードが申告するNodeNetworkInfoのhostに何が入るか(非公開ノードでLAN内IPがそのまま出るか)
- 台帳の中身をログやcodablectrlで見られるか
- 掘れたブロックを配る役目が誰になったか(967b7ebはマイナーが同一ゾーンへ一斉送信。2026-10-24の設計変更で投票ノードが「自分の番」で流す方向)
-->
