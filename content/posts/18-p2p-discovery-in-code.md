---
title: "Codablecashのソースコードで、ノードが「仲間」を見つける仕組みを追う"
slug: "p2p-discovery-in-code"
date: 2026-11-08T12:00:00+09:00
draft: false
tags: ["暗号資産", "Codablecash"]
cover:
  image: "images/p2p-discovery-top.png"
  alt: "丸い顔のノードが2つ、手をつないでいるイラスト"
---

[前回](/posts/p2p-discovery/)は、ノードの起動〜停止までをテストコードから追いました。今回は同じことを、実際のソースコードから読んでゆきます。

<!-- 前回の冒頭で触れた開発者さんの投稿「P2PネットワークのDNS部分を見直しています」の、**DNSの正体**を見る回でもあります。 -->

記事内のコード引用は、前回と同じく**Codablecash**のソースコード[`967b7eb`](https://github.com/alinous-core/codablecash/tree/967b7eb4fc41c568a2c2b05cc63018b51e0d3fa5)（2026年9月8日）のコミットからお借りしています。

{{< tips title="※">}}
Codablecashは開発中のプロジェクトです。ここでご紹介するコードは本番で変わっている可能性があります
{{< /tips >}}

## ノードの動き

<!-- 前回読んだテスト（`src_test/blockchain/testnet/test_first_net.cpp`）では、ノードの起動から終わりまでは、おおまかに以下のような流れになっていることがわかりました。 -->

<!-- | 台本 | 起きていたこと |
|---|---|
| 台本0 | 3台ぶんの設定を作り、鍵（`NodeIdentifierSource`）から名札（`NodeIdentifier`）を取り出す |
| 台本1 | 1台目が空のシーダーで`startNetwork()`。自分の連絡先をシーダーに入れる |
| 台本2 | 2台目が1台目入りのシーダーで`startNetwork(&seeder, true)`、`syncNetwork()`。`CHECK`で双方向につながっていることを確認 |
| 台本3 | 3台目も同様に起動し、3台全員がつながる。高さ5まで待って逆順に`shutdown()` |

そして、前回の終わりに残した宿題がこれでした。

- `startNetwork()`の中では、何がどういう順番で起きているのか
- シーダーに入っているのは1件か2件だけなのに、ノードはそれ以上の相手をどうやって知るのか
- なぜ、つなぎに行っていない側（1台目）にも接続が登録されるのか。名乗りはどう確かめているのか
- 2台目以降が`startNetwork()`に渡している`true`は何か
- 「やめます」を受け取ったノードは何をするのか -->

これから見てゆくノードの動きは、大まかに以下のようになっています。

1. 自分の名札を用意する
2. 待ち受けスタート
3. 最初に連絡する相手（シード）を知る
4. 3の相手に一時的に接続し、他のノードの連絡先が載った「電話帳」をもらう
5. 電話帳から何台か選んで、ノード仲間としてつなぐ
6. つないだらご挨拶。双方の処理を行う。
7. 仲間の情報に追いついて（同期して）、日常の動きに入る
8. 退出

## 関連するクラス

ノードに関連するクラスは、`src_blockchain_p2p/`配下と、`src_blockchain/bc_network_instance/`配下にいました。

- `NodeIdentifier` ： ノードの名札
- `P2pNodeRecord` ： 連絡先1件分（ゾーン・名札・ホスト・ポート・プロトコルなどを持つ）
- `INetworkSeeder`/`ArrayNetworkSheeder` ： 最初の連絡先を渡す「シーダー」
- `P2pDnsManager`/`P2pNodeDatabase` ： 電話帳の窓口担当と、ノードが保有する「MY電話帳」
- `BlochchainP2pManager` ： 接続まわりの管理担当（接続中のノード仲間・一般客、一斉送信など）
- `DownloadDnsInfoCommand` ： 相手ノードの電話帳の一部をコピーさせてもらうためのコマンド
- `ConnectNodeSelector` ： 電話帳から接続先を選ぶ
- `LoginPubSubCommand` / `NodeNetworkInfo` ： ノードにつながるためのコマンドと、そのとき添える自分の名刺
- `DnsCheckCommandMessage` ： 名刺を受け取った側のノードが相手に折り返して確認
- `NodeShutdownCommand` ： 退出を通知するコマンド

## 1. ノードの名札は公開鍵

まず、ノードは自身の名札である`NodeIdentifier`を用意します。

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

メンバ変数の名前は`nodeIdentifier`ですが、コメントに`pubkey`とある通り、中身は**公開鍵**のようです。対になる秘密鍵は`NodeIdentifierSource`が持っていて、ノードはこの鍵でログインや各種の通知に署名します。

```cpp
// src_blockchain/bc_network/NodeIdentifierSource.h
class NodeIdentifierSource : public IBlockObject {
public:
	// ・・・・・
	static NodeIdentifierSource* create();              // 鍵のペアを新しく作る
	NodeIdentifier toNodeIdentifier() const noexcept;   // 公開鍵から名札を作る
	const BigInteger* getSecretKey() const noexcept;    // 署名に使う秘密鍵
	// ・・・・・
private:
	IKeyPair* pair;   // 秘密鍵と公開鍵のペア
};
```

「名札」といっても「好きに付けられる名前」ではなく、「署名ができる名札」のようです。これは[ステーキングの記事](/posts/staking-in-code/)で出てきた、投票プールを登録するときの`NodeIdentifier`と同じものです。

## 2〜3. 待ち受け・最初につながる相手

ネットワークの開始となる、`CodablecashNetworkNode::startNetwork()`の中身が以下です。

```cpp
// src_blockchain/bc_network_instance/CodablecashNetworkNode.cpp
void CodablecashNetworkNode::startNetwork(INetworkSeeder* seeder, bool pending) {
	// ・・・・・
	// startNetwork
	const UnicodeString* host = this->nwconfig->getHost();
	int port = this->nwconfig->getPort();

	this->inst->startNetwork(host, port);   // 待ち受けを始める

	// start processors
	{
		const NodeIdentifierSource* networkKey = this->nwconfig->getNetworkKey();
		this->inst->startProcessors(networkKey, pending);   // 届いた命令を処理する担当たちを起こす（pendingは7で）
	}

	// init database
	if(seeder != nullptr){
		ArrayList<P2pNodeRecord>* seedList = seeder->getSeedNodes(); __STP(seedList);
		// ・・・・・
		if(seedList != nullptr && !seedList->isEmpty()){
			initDatabase(seedList);    // シーダーの連絡先から電話帳を作る
		}
	}

	// init connections
	maintainNetwork();     // 電話帳から選んで接続する
}
```

引数で渡されている`INetworkSeeder`が「最初につながる相手」のリストです。中身は以下のようになっていて、連絡先（`P2pNodeRecord`）のリストが配列で入っています。

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

さらにそのリストの中の1件分の`P2pNodeRecord`を見てみると、以下のような情報が入っています。

| 項目 | 中身 |
|---|---|
| `zone` | ゾーン番号 |
| `nodeId` | 名札（公開鍵） |
| `canonicalName` | 人間向けの名前 |
| `protocol` | `TCP_IP_V4`か`TCP_IP_V6`か |
| `host` / `port` | 接続先のアドレスとポート |
| `createdTime` / `lastUpdatedTime` | 登録・更新の時刻 |
| `list` | ゾーンごとの、つながっている相手 |

1台目となるノードは最初に連絡する相手がいないので、シーダーは空で起動します。そのためこういった連絡先リストを処理する流れは2台目以降になります。

## 4. 最初の相手から「電話帳」をもらう

ノードは、まだ見ぬ多数のノードとつながる必要があります。その相手をどのように知るのでしょう。

まず、シードとして「最初につながる相手」の連絡先をもらったノードは`initDatabase()`→`P2pDnsManager::importSeeds()`でその相手に接続します。そして、**その相手が持っている電話帳**をもらいに行きます。

自分自身は1件（もしくは少し）しか他のノードを知らなくても、そのノードの知り合いを紹介してもらうイメージです。

```cpp
// src_blockchain_p2p/bc_p2p_info/P2pDnsManager.cpp
void P2pDnsManager::importSeeds(int numZone, const P2pNodeRecord *nodeRecord, ISystemLogger *logger) {
	// ・・・・・
	const UnicodeString* host = nodeRecord->getHost();
	int port = nodeRecord->getPort();

	try{
		for(int i = 0; i != numZone; ++i){
			doImportSeeds(i, host, port, logger);     // ゾーンごとに電話帳をもらう
		}

		// add seed
		this->database->importUnconnectedNode(nodeRecord);   // シード自身も電話帳に入れる
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
			this->database->importUnconnectedNode(rec);   // もらった連絡先を自分の電話帳へ
		}
	}
}
```

`P2pDnsManager`なるものが、個々のノードが所有する「MY電話帳」の窓口担当です。

その`P2pDnsManager`が呼んでいる`P2pClient`は、ウォレットがノードから電話帳をもらうときにも使われている「一般客」としての接続です。接続には`LoginClientCommand`を使っていて、電話帳をもらったらすぐに切ります。

### 「接続」の種類

`P2pClient`は「一般客」としての接続だと書きましたが、このあと6章で出てくる『ノード仲間』としての接続とは、以下のように使うコマンドが違います。

- `LoginClientCommand`（`P2pClient`が使う）：「こんにちは〜、電話帳ください」と一般客としてつながる
- `LoginPubSubCommand`（6章）：「私もノードです、こんにちは〜」と名刺を添えて仲間としてつながる

つまり、まだ誰ともつながっていないノードは、いきなり「私も仲間です」とつながるのではなく、まずは一般客として接続し、「すみませんが、お知り合いのノードのリストをくださいな」と伺って、そのノードの持っている電話帳をコピーさせてもらって帰る、という手順になっているようです。

そして、ここでもらえる電話帳のリストには上限があり、1回の`DownloadDnsInfoCommand`で**最大256件**となっていました。

```cpp
// src_blockchain_p2p/bc_p2p_cmd_client/DownloadDnsInfoCommand.cpp
DownloadDnsInfoCommand::DownloadDnsInfoCommand(uint16_t zone) : AbstractClientRequestCommand(TYPE_CLIENT_DOWNLOAD_DNS) {
	this->zone = zone;
	this->maxNum = 256;
}
```

「知り合いノードのリストをください」と言われた側のノードは、自分の`P2pDnsManager`から該当ゾーンの連絡先を取り出して返しています。

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

<!-- 台本に当てはめると、3台目が起動したとき、シーダーには1台目と2台目の連絡先が入っています。3台目はそれぞれにお客さんとして聞きに行き、相手の台帳をもらってから、シード自身も台帳に入れる。この時点で3台目の台帳には1台目と2台目が載っている、という状態になります。ノードが増えてくれば、シーダーに1件しかなくても、その1件から数百件の電話帳がもらえる、という仕組みです。 -->

こうしてゲットした電話帳は`P2pNodeDatabase`によってノードのデータフォルダの中にファイルとして保存されています。一度手に入れた電話帳のリストは自身でもちゃんと保有して、ノードを終了・再起動しても手元に残る、ということのようです。

 <!-- こうしてゲットした接続先リストは、ノードのデータフォルダの中にB木（P2pNodeDatabase）として保存されています。B木はデータベースでよく使われる保存の仕組みで、辞書のつめ見出しのように「どの範囲がどこにあるか」の目次を持っているので、件数が増えても目的の1件をすぐ探せます。一度もらった電話帳は再起動しても手元に残る、ということですね。 -->

## 5. 電話帳から選んでつなぐ

ここまでで、やっと「MY電話帳」が用意できました。この時点ではまだノードとしては誰とも繋がっていない状態です（先ほどリストを受け取ったときは来客窓口から声をかけただけで、ノードとしての接続ではない）。なので今からやっと仲間と接続します。

`startNetwork()`の最後で呼ばれていた`maintainNetwork()`が、ゾーンごとに「あと何本足りないか」を数えて、足りないぶんだけ電話帳から選んでつなぐ形になります。この接続には目標の本数があって、以下で設定されていました。

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

**自分のゾーン（numConnectionOwnShard）に8本、ほかの各ゾーン（numConnectionExtShard）に4本**になるまで、自分からつなぎに行くようです。

ではいよいよ接続作業です！まずは接続相手を選びます。

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
		selector.importCandidates(list);          // 電話帳に載っている連絡先を候補にする

		while(diff > 0 && selector.hasNext()){
			const P2pNodeRecord* rec = selector.fetchNext();   // 1件選ぶ

			if(__connectWithP2pNodeRecord(rec)){  // つながったら
				diff--;                           // 残りを減らす
			}
		}
	}
}
```

ゾーンごとの目標本数と今つながっているノードの数を出して、目標に足りていない分だけ電話帳から取ってきて接続を繰り返します。

最後の`if(__connectWithP2pNodeRecord(rec))`は接続が成功したかどうかをチェックしていて、成功したら「あと何本」の残りを減らしています。接続失敗ならカウントせず次の相手に接続、という形です。

電話帳からどうやって接続相手をピックアップするかというと、以下の`ConnectNodeSelector::fetchNext()`がそれを担っていました。候補の中からくじ引きのようにランダムに1台ずつ選んで、一度選んだ相手は候補から外しています。

<!-- 候補を読み込んだ時点の時刻をSHA-256にかけて大きな数を1つ作り、それを「残っている候補の数」で割った余りを添字にして1件ずつ取り出していました。取り出した候補は候補から外れるので、同じ相手が二度選ばれることはありません。 -->

```cpp
// src_blockchain_p2p/bc_p2p_selector/ConnectNodeSelector.cpp
const P2pNodeRecord* ConnectNodeSelector::fetchNext() const {
	int index = toIndex(this->candidates->size());
	P2pNodeRecord* record = this->candidates->remove(index);   // 取り出した候補は候補から外す
	this->usedCandidates->addElement(record);
	return record;
}
```

## 6. ノード接続時、双方のうごき

ついにノード同士でつながります。このときの、つなぐ側と、それを受け取る側両方の動きをそれぞれ見てゆきます。

### つなぐ側: 名刺を添えてご挨拶

つなぐ側の視点、`loginNode()`から。

まず、相手ノードに回線をつないだら、`LoginPubSubCommand`でご挨拶を送ります。`LoginPubSubCommand`という名前ですが、ログインといっても一般的なIDやパスワードを使うものではなく、「私はこの名札（公開鍵）のノードです」とご挨拶するような形式のものです。このときに自分の連絡先が書かれた名刺（`NodeNetworkInfo`）を添えています。

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

		NodeNetworkInfo info(zoneSelf, &nodeId, &tm, protocol, host, port);   // 名刺を準備
		info.setCanonicalName(this->nodeName);

		cmd.setNodeNetworkInfo(&info); 
	}

	cmd.sign(source);   // 自分の鍵で署名

	AbstractCommandResponse* response = handshake->publishCommand(&cmd); __STP(response); // 「こんにちは、私もノードです（名刺スッ）」
	// ・・・・・
	uint32_t type = response->getType();
	if(type != AbstractCommandResponse::TYPE_RES_OK){
		throw new P2pHandshakeAuthenticationException(L"Already connected.", __FILE__, __LINE__);
	}
}
```

接続のための準備を色々と行って、後半の`handshake->publishCommand(&cmd)`が相手ノードに送信している箇所です。その後の`response->getType()`で相手ノードからの返事が`OK`でなければ、「もうつながっている」として例外を投げています。

### 受ける側: 相手確認と登録

次は、接続を受ける側の視点です。挨拶を受けたノード側では、`LoginPubSubCommand::execute()`が実行されます。

```cpp
// src_blockchain_p2p/bc_p2p_cmd/LoginPubSubCommand.cpp
AbstractCommandResponse* LoginPubSubCommand::execute(const PubSubId* pubsubId, IPubsubCommandListner *listner) const {
	try{
		checkSignature();  // 1. 署名が名札（公開鍵）と合うか
	}
	catch(Exception* e){
		delete e;
		return new SignatureErrorResponse();
	}

	{
		// ・・・・・
		BlockchainNodeHandshake* node = p2pMgr->getNodeHandshakeByNodeId(this->nodeId);
		StackHandshakeReleaser __releaser(node);
		if(node != nullptr){    // 2. 同じ名札がもうつながっていたら断る
			ErrorPubsubResponse* res = new ErrorPubsubResponse();
			return res;
		}
	}

	listner->fireExecuteCommand(pubsubId, this);   // 3. 接続として登録

	// check & register dns
	if(this->nodeNetInfo){    // 4. 名刺を担当に回す
		// ・・・・・
		netDnsProcessor->requestDnsCheck(this->nodeNetInfo);
	}

	OkPubsubResponse* res = new OkPubsubResponse();
	return res;
}
```

やっていることを順番書くと、

1. **署名の確認**：`checkSignature()`で名札（公開鍵）から署名を確かめます。なりすましはここで弾かれます
2. **二重接続チェック**：`getNodeHandshakeByNodeId()`ですでに繋がっているノードIDをチェックして、もし同じ鍵のノードがすでに接続済みならエラーとします
3. **接続中リストに登録**：`fireExecuteCommand()`で、接続中の相手を管理する`BlochchainP2pManager`に相手を登録してもらう
4. **MY電話帳に登録**：もらった名刺を別の担当に回して、相手ノードの確認ができたらMY電話帳（`P2pDnsManager`）にも登録

4の「確認」とはなにかというと、「このノードに接続できるかな？」の確認です。`DnsCheckCommandMessage::checkAndRegister()`で以下のようにしています。

```cpp
// src_blockchain_p2p/bc_p2p_processor/DnsCheckCommandMessage.cpp
void DnsCheckCommandMessage::checkAndRegister(P2pRequestProcessor* processor, ISystemLogger* logger) {
	{
		IClientSocket* con = this->nodeNetInfo->getConnection(); __STP(con);   // もらった名刺の連絡先に自分から接続してみる
		StackConnectionCloser _st_closer(con);

		ExceptionThrower<PubsubNetworkException>::throwExceptionIfCondition(!con->isConnected(), L"Connection does not reach.", __FILE__, __LINE__);
	}

	// dns check
	P2pDnsManager* dnsManager = processor->getP2pDnsManager();
	dnsManager->updateOrAddRecord(this->nodeNetInfo, logger);   // 届いたときだけ電話帳に登録
}
```

**名刺に書かれた連絡先に自分からつなぎ直してみて、ちゃんと接続できたときだけ**、MY電話帳に登録します。届かなければ例外になって、電話帳には登録されません。

ここで、「今つながっている相手に自分からつなぎ直したらつながらない、なんてことあるのかな？」と思ったのですが、**外から届かないノード**だった場合はこのケースに当てはまるようです。ノード自身はプログラムの中で待ち受けを開始しますが、ルーターやファイアウォールなどの設定で外部からのアクセスを拒否している、という場合があります。

- 外からは届かないノードでも → 他のノードに「もしもし」と声をかけることは可能
- 外からは届かないノードなら → 他のノードから「もしもし」はできない（相手の電話帳には載らない）

## 7. つながったあと

無事に仲間とつながったあとは、仲間のブロックに追いつくための同期が始まります。`syncNetwork()`ですね。

```cpp
// src_blockchain/bc_network_instance/CodablecashNetworkNode.cpp
void CodablecashNetworkNode::syncNetwork() {
	NetworkNodeSync sync(this);
	sync.sync();                                 // 仲間に追いつく

	this->inst->resumeRequestProcessor();        // 保留箱を片付けて、保留モードを解除する
}
```

`sync.sync()`の部分は、ゾーンごとに「つながっているノードから3台（`numInitialSyncNodes`で定義）をランダムに選び、それぞれからブロックヘッダをもらう。自分のゾーンだけは、ブロックの中身も取りに行く」という動きになっているようです。

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

そして`syncNetwork()`の最後で呼ばれている`resumeRequestProcessor()`についてです。これは処理を再開させる関数ですが、「再開」ってなにかというと、「止めておいた処理の再開」を指します。

止めておいた処理とは何かというと、改めてネットワーク開始時の関数`CodablecashNetworkNode::startNetwork(INetworkSeeder* seeder, bool pending)`を見てください。第二引数が`bool pending`となっています。

<!-- 担当のスレッドの仕事のループです。

```cpp
// src_blockchain_p2p/bc_p2p_processor/P2pRequestQueueProcessorThread.cpp
if(!this->suspend && !this->queue->isEmpty()){
	cmd = this->queue->fetchFirst();   // 吊るさないなら処理する
}
else{
	lock->wait();  // 吊るすなら今は何もせず待つ
}
``` -->

2台目以降のノードは、この`pending`（保留中）を`true`にしてネットワークを開始していました。これは「まだ仲間に追いついていないので、届いた新着のお知らせ（新しいブロックや取引）は、ひとまず保留箱に溜めておく」という指定です。なんでかというと、ノード起動は、次の順番で進む必要があるからです。

1. 保留モードでネットワークにつながる（`startNetwork(&seeder, true)`）
2. 仲間からブロックをもらって追いつく（`sync()`）
3. 追いついたら、保留箱に溜まったお知らせを片付けて、保留モードを解除する（`resumeRequestProcessor()`）

古いデータのまま新着を処理し始めないように、まずは追いつくことを優先しているのですね。逆に1台目は追いつく相手がいないので`false`で、最初から保留なしで動いています。


## 8. ノードを停止するとき

最後は、ノードの停止時です。停止する側のノードはトラブルでなければ自分の意思で停止します。その停止と、「停止します」を受け取った仲間ノードは何をするのかを見てゆきます。

<!-- 前回見たとおり、台本3の`shutdown()`は仲間に知らせずに止まるだけで、知らせるほうは`broadCastShutdownCommand()`という別の関数でした。

```cpp
// src_test/blockchain/testnet/test_sync_header_only.cpp
	CodablecashNetworkNode node01(dirNode01, config01, &logger);
	{
		// ・・・・・
		node01.startNetwork(&seeder, true);

		node01.syncNetwork();
		// ・・・・・（高さ8を超えるまで待つ）
	}

	node01.broadCastShutdownCommand();  // 「停止します」を仲間に流す
}
``` -->

まずは停止する側です。停止を仲間に広めるのは`broadCastShutdownCommand()`という関数です。「私は止まります」というお知らせに自分の鍵で署名して、全ゾーンの仲間に流しています。

```cpp
// src_blockchain/bc/CodablecashNodeInstance.cpp
void CodablecashNodeInstance::broadCastShutdownCommand(const NodeIdentifierSource *source) {
	NodeShutdownCommand command;

	NodeIdentifier nodeId = source->toNodeIdentifier();

	command.signTimestamp(source);   // 時刻に署名
	command.sign(source);            // 本体に署名

	this->p2pManager->broadCastAllZones(nullptr, &command, this->p2pRequestProcessor);   // 全ゾーンへ
}
```
<!-- 
ところで、`broadCastAllZones()`から先をたどっても、実際に送っている行がなかなか見つかりませんでした。実は「全員に送る」と言いながら、この関数自身は送っていません。相手ごとに「この相手に送って」という依頼メモを作って、作業係の箱に入れるところまでで終わっているようです。

```cpp
// src_blockchain_p2p/bc_p2p/P2pZone.cpp
// （broadCastAllZones() から、ゾーンごとに呼ばれる）
void P2pZone::generateTransferRequest(const NodeIdentifier *excludeNodeId, const AbstractNodeCommand *command, P2pRequestProcessor *processor) {
	// ・・・・・
	for(int i = 0; i != maxLoop; ++i){   // つながっている相手の数だけ
		// ・・・・・
		nodeTransferProcessor->reserveTransfer(nodeId, command);   // 「この相手に送って」と依頼
	}
}

// src_blockchain_p2p/bc_p2p_processor/NetworkTransferProcessor.cpp
void NetworkTransferProcessor::reserveTransfer(const NodeIdentifier *nodeId, const AbstractNodeCommand *command) {
	NetworkTransferNodeCommand* messageCommnad = new NetworkTransferNodeCommand(nodeId, command);   // 依頼メモを作る
	// ・・・・・
	this->executor->addCommandMessage(messageCommnad, num);   // 作業係の箱に入れて、おしまい
}
```

箱に入った依頼メモは、別のスレッドで待機している作業係（`CommandProcessUnit`）が取り出して実行します。

```cpp
// src_blockchain/procesor_multi/CommandProcessUnit.cpp
while(isRunning() || !checkListIsEmpty()){
	// ・・・・・
	if(!this->list.isEmpty()){
		cmd = this->list.remove(0);   // 箱から1枚取り出す
	}
	else{
		// ・・・・・
		lock->wait();                 // 空なら、次の依頼が来るまで待つ
	}
	// ・・・・・
	if(cmd != nullptr){
		processCommand(cmd);          // 中で cmd->execute() を呼ぶ
	}
}
```

ここで動く`execute()`は、さきほど箱に入れた`NetworkTransferNodeCommand`のものです。その中で相手との接続を探して、`sendCommnad()`でようやく「停止します」を送っています。

つまり、送るまでの流れはこうなっています。

1. `broadCastAllZones()`：ゾーンごとに
2. `P2pZone::generateTransferRequest()`：つながっている相手ごとに依頼
3. `NetworkTransferProcessor::reserveTransfer()`：依頼メモを箱に入れる
4. 作業係（`CommandProcessUnit`）：箱から取り出して`execute()`
5. `NetworkTransferNodeCommand::execute()`：実際に送る

3と4の間は関数呼び出しでつながっていないので、コードを順に追っていくと途中で道が途切れたように見えます。6章で名刺を「担当に回す」と書いた`requestDnsCheck()`も、同じ箱と作業係の仕組みを使っていました。 -->

そして、そのお知らせを受け取ったノード側の処理がこちらの`NodeShutdownCommand::executeAsNode()`です。

```cpp
// src_blockchain_p2p/bc_p2p_cmd_network/NodeShutdownCommand.cpp
AbstractCommandResponse* NodeShutdownCommand::executeAsNode(BlockchainNodeHandshake *nodeHandShake, CodablecashNodeInstance *inst, bool suspend) const {
	{
		bool vl = verifyTimestamp();   // 本人の署名か
		// ・・・・・
	}

	bool updated = updateShutdownNode(inst);   // 電話帳から消して、接続を切る

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

「停止します」を受け取ったら、まずは相手を電話帳から消して、接続を切る。そして自分の仲間にも転送する、という流れです。この転送は`hops`でカウントしていて、5回までとなっていますね。

ここでも署名を確かめているので、他人が勝手に「あのノードはやめました」という知らせを作ることはできない設計です。

## おわりに

もう少し要点を絞って挙げられるといいのですが、関連コードを並べすぎて読みにくくなっていたらすみません（コードが壮大すぎて追いかけるだけで精一杯気味です）。

でも、こうして1つずつ追ってみたことでノードが何をしているのかがうっすら理解できました。最初の1つのノードからスタートして、それぞれのノードがだんだんと手をつないで・・・と想像するととても面白く、シナプスを想起させるような、不思議な感じがしますね。

<!-- | 段階 | やること | 数字（967b7eb時点） |
|---|---|---|
| 名札 | 公開鍵をノードIDにする | — |
| 最初の相手 | シーダー（`INetworkSeeder`）に入っている連絡先 | 呼び出し側が指定 |
| 電話帳 | 最初の相手から台帳をもらう | ゾーンごとに最大256件 |
| 接続 | 台帳からランダムに選んでつなぐ | 自分のゾーン8本、ほかのゾーン4本（テストでは2本・2本） |
| 名乗り | ログインに連絡先を添えて署名。受けた側は折り返して確認 | 届かなければ台帳に載らない |
| 追いつき | 仲間から3台選んでヘッダをもらう | 3台 |
| 退出 | 署名つきの通知を全ゾーンへ。転送は5回まで | 5ホップ |

読んでみて思ったのは、「どうやって見つけるか」の答えは意外とシンプルで、**最初の1件だけは人間が教える。あとは電話帳を交換して、ランダムに選んでつなぐ**、ということでした。Bitcoinとの大きな違いは、その「最初の1件」をソフトに埋め込んでいるか、起動時に渡しているか、という点で、Codablecashの967b7ebの時点では後者です。公開版で「開発者さんのシードノードをどう指定するのか」が、テストネットに参加するときの最初のハードルになりそうです。

前回の冒頭で引いた開発者さんの投稿にあった「DNS部分の見直し」は、まさにこの電話帳（`P2pDnsManager`）まわりの話だと思います。今回読んだ「もらう・確認して載せる・退出で消す」のうち、どこが変わるのか。公開版が出たらこの記事と見比べてみるつもりです。 -->

<!-- 公開版で確かめたいこと(記事には載せない作業メモ)
- シードノードの指定方法(設定ファイル/CLI)。チェックリスト14
- 所属ゾーンの指定方法と初期ゾーン構成。チェックリスト16
- 自ノードが申告するNodeNetworkInfoのhostに何が入るか(非公開ノードでLAN内IPがそのまま出るか)
- 台帳の中身をログやcodablectrlで見られるか
- 掘れたブロックを配る役目が誰になったか(967b7ebはマイナーが同一ゾーンへ一斉送信。2026-10-24の設計変更で投票ノードが「自分の番」で流す方向)
- 本番のshutdown経路でbroadCastShutdownCommand()が呼ばれるか(967b7ebではテストが明示的に呼んでいる)
-->
