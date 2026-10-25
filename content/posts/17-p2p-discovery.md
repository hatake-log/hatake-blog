---
title: "Codablecashのテストコードから、ノードの起動〜終了を追う"
slug: "p2p-discovery"
date: 2026-10-25T20:40:00+09:00
draft: false
tags: ["暗号資産", "Codablecash"]
cover:
  image: "images/p2p-discovery-top.png"
  alt: "丸い顔のノードが2つ、手をつないでいるイラスト"
---

[前回](/posts/ticket-lock-period/)・[前々回](/posts/staking-in-code/)はステーキング関連のコードを読みましたが、今回は**ノード**の動きに注目します。

暗号資産（仮想通貨）のネットワークには、中心となるサーバーがありません。そのため、参加している個々のノードが互いにつながって、新しいブロックやトランザクションについて「ねぇねぇ、こんなのが来たよ」と伝播し合っている・・・というイメージがP2P（ピア・ツー・ピア）にはあると思いますが、実際のコードではどうなっているのでしょう。




<!-- きっかけは、開発者さんの2026年10月のこの投稿でした。

> [Codablecash進捗]
> P2PネットワークのDNS部分を見直しています。
> ここがしっかり出来ると、安定系に突入でき、テストネットがスムーズにたちがあります。
>
> —— [@iizuka](https://x.com/iizuka)（2026年10月12日ごろの投稿）

「DNS」と聞くと、ドメイン名からIPアドレスを調べるインターネットのあれを思い浮かべますが、コードを読んでみると、ここでいうDNSは**各ノードが持っている「ほかのノードの連絡先の台帳」**のことでした。見直し中、ということは今のコードは変わる前提です。だからこそ、変わる前の形を一度ちゃんと読んでおけば、公開版が出たときに「何が変わったのか」が分かるはず、というのが今回の動機です。

この話は長くなったので、2回に分けます。**今回は、上流のテストコードを「台本」として読んで、ノードが起動してから止まるまでに何が起きるかを掴む回**。次回は、その台本の各行の裏でどのクラスが何をしているかをソースで追う回です。 -->

記事内のコード引用は、Codablecashのソースコード[`967b7eb`](https://github.com/alinous-core/codablecash/tree/967b7eb4fc41c568a2c2b05cc63018b51e0d3fa5)（2026年9月8日）のコミットからお借りしています。

<!-- {{< tips >}}
Codablecashは開発中のプロジェクトで、今回の部分はとくに開発者さんが「見直している」と明言している箇所です。ここに出てくる数値や手順は公開版で変わっている可能性が高いので、「どういう考え方で仲間を見つけているのか」の骨格を読む、くらいの気持ちでお付き合いください。

また、前回までと同じく、私はPHPを少し触るくらいでC++の知識はありません。クラス名と短いコードを眺めて「ふーむ」と言う回です。
{{< /tips >}} -->

<!-- ## 「仲間を見つける」とは

暗号資産（仮想通貨）のネットワークには、中心になるサーバーがありません。

参加しているノード（ソフトを動かしているコンピュータ）が互いにつながって、新しいブロックやトランザクションについて「ねぇねぇ、こんなのが来たよ」と回し合っています。これがP2P（ピア・ツー・ピア）です。

ここで気になるのが、今回のテーマでもある**いちばん最初、誰ともつながっていないノードは、相手をどうやって知るのか。**という部分です。

Bitcoinの場合は、開発者がソフトの中にいくつかの「とりあえずここに聞け」という宛先（シード）を埋め込んでいて、起動したノードはそこに聞いて他のノードの一覧を手に入れます。このあたりは[Binary Igorさんの記事](https://binaryigor.com/bitcoin-p2p-network.html)がとても丁寧で、今回の記事もかなり影響を受けています。

では、Codablecashはどうなっているのか見てみましょう。

{{< tips title="先に「ゾーン」の説明" color="sky" >}}
Codablecashのコードにはいたるところに`zone`という言葉が出てきます。これはネットワークを複数の区画に分けて並行して動かす設計（いわゆるシャーディング）の区画のことです。ノードは起動時に自分の所属ゾーンを1つ持ち、他のゾーンとも少しだけつながります。

今回の記事では「自分のゾーン」と「ほかのゾーン」で接続の数が違う、というところにだけ関わってきます。最初のテストネットがいくつのゾーンで始まるかは、この記事を書いている時点では分かりません。
{{< /tips >}} -->

## テストコードを読む

ここまでの記事では対象のクラスを1つずつ追う形でしたが、今回は少しやり方をかえて、テストコードから読んでみることにします。

私のブロックチェーンの知識が浅いということに加え、マイニングでもない、ステーキングでもない、何しているのかあまりよくわからない**ノード**という存在がいまいちピンとこず・・・。そこでまずは、1つのファイル内に上から順にシナリオが書かれたテストコードを追ってみることにした次第です。

Codablecashの`src_test/`には、3台のノードを起動して互いにつなぐ`test_first_net.cpp`というテストファイルがあります。ノード起動〜終了の流れが書かれていますが、少し長いテストなので4段落に区切って見てゆきます。

<!-- 上から下へ台本のように並んでいて、しかも「3台を立てたら全員がつながっているはず」という**期待する結果**が`CHECK`という形で先に書いてあります。C++の中身は読めなくても、台本と`CHECK`なら読める。まず「何が起きるか」をここで頭に入れてから、次回「どう起きているか」をソースで確かめる、という順番です。 -->

<!-- ## テストファイルの構成

先に、このファイルの構造を少しだけ。私と同じくC++に不慣れな方向けに、PHPのテスト（PHPUnit）に置き換えると、こうなります。

- `TEST_GROUP(TestFirstNetGroup){ ... }` — テストのグループ。テストクラスに相当し、中の`TEST_SETUP`/`TEST_TEARDOWN`が各テストの前後処理
- `TEST(TestFirstNetGroup, case01){ ... }` — そのグループに属する**テスト1本**。テストメソッド1つに相当し、このファイルにあるテストはこの1本だけ
- `CodablecashNetworkNode node01(dirNode01, config01, &logger);` — テストの区切りではなく、変数の宣言。`$node01 = new CodablecashNetworkNode(...)`に相当します。C++では「型名 変数名(引数)」と書くと、その引数で初期化しながら変数を作る、という意味になります
- 途中に何度も出てくる`{ ... }`だけのブロック — if文でも関数でもなく、変数の生存範囲を区切る「段落」。抜けると中で作ったものが自動で片付けられます
- `CHECK(条件);` — 個々の検証。`assertTrue()`に相当し、1つでも偽ならcase01全体が失敗

{{< tips title="関数呼び出しと変数宣言の見分け方" color="sky" >}}
括弧の直前に単語が**1つ**なら関数呼び出し（`env->setup()`、`node01.startNetwork(...)`、`P2pNodeRecord::createIpV6Record(...)`）。`.`や`->`はPHPの`->`、`::`はPHPの`::`と同じ感覚です。

括弧の直前に単語が**2つ**なら変数の宣言（`CodablecashNetworkNode node01(...)`）。1つめが型、2つめが新しく作る変数の名前です。`P2pNodeRecord* rec = ...`の`*`は「その型を指すポインタ」の印で、PHPの変数が常にオブジェクトへの参照であるのと似た感覚で読んで大丈夫です。
{{< /tips >}}

つまり以下は1本のテストで、3台のノードを段落ごとに順に立てているものです。長いので、私のほうで4つに切って見ていきます（引用は適宜省略しています）。 -->

## テストの準備

さっそくテストコードです。以下はテストの冒頭箇所で、色々なパラメータやインスタンスを準備しているようです。

```cpp
// src_test/blockchain/testnet/test_first_net.cpp
TEST(TestFirstNetGroup, case01){
	// ・・・・・
	CodablecashSystemParam param;
	DebugCodablecashSystemParamSetup::setupConfig02(param);   // テスト用のパラメータ

	CodablecashNetworkNodeConfig nwconfig;
	nwconfig.setSysConfig(&param);

	// network config
	CodablecashNetworkNodeConfig* config01 = new CodablecashNetworkNodeConfig(nwconfig); __STP(config01);
	config01->setCanonicalName(L"node_01");
	CodablecashNetworkNodeConfig* config02 = new CodablecashNetworkNodeConfig(nwconfig); __STP(config02);
	config02->setOriginalNwtworkKey();     // 2台目のネットワークキーを新しく作る
	config02->setCanonicalName(L"node_02");
	CodablecashNetworkNodeConfig* config03 = new CodablecashNetworkNodeConfig(nwconfig); __STP(config03);
	config03->setOriginalNwtworkKey();     // 3台目のネットワークキーを新しく作る
	config03->setCanonicalName(L"node_03");
	// ・・・・・（1台目にウォレット・最初の残高・マイナーの設定、そしてネットワークキーを作る）
		NodeIdentifierSource* networkKey =  NodeIdentifierSource::create(); __STP(networkKey);
		config01->setNetworkKey(networkKey);
	// ・・・・・

	NodeIdentifier nodeId01 = config01->getNodeId();   // ネットワークキーからノードIDを取り出す
	NodeIdentifier nodeId02 = config02->getNodeId();
	NodeIdentifier nodeId03 = config03->getNodeId();
```

テストで使う3台ぶんのノードの設定です。それぞれにノード固有の**ネットワークキー**（`NodeIdentifierSource`）を持たせ、最後に`config01->getNodeId()`の部分で**ノードID**（`NodeIdentifier`）を取り出しています。

<!-- 鍵を持たせている行は、2台目・3台目では`setOriginalNwtworkKey()`、1台目では`NodeIdentifierSource::create()`で作った鍵を`setNetworkKey()`に渡す2行、と書き方が違いますが、やっていることは同じです。`setOriginalNwtworkKey()`の中身を見ると、新しい鍵（`NodeIdentifierSource`）を作って`setNetworkKey()`に渡しているだけでした。

```cpp
// src_blockchain/bc_network_instance/CodablecashNetworkNodeConfig.cpp
void CodablecashNetworkNodeConfig::setOriginalNwtworkKey() noexcept {
	NodeIdentifierSource* keys = NodeIdentifierSource::create(); __STP(keys);
	setNetworkKey(keys);
}
``` -->

ノードIDとは、ランダムな番号ではなく先述のネットワークキーから作られた**公開鍵**を指しているようです。以下の箇所で取り出していました。

```cpp
// src_blockchain/bc_network_instance/CodablecashNetworkNodeConfig.cpp
NodeIdentifier CodablecashNetworkNodeConfig::getNodeId() const noexcept {
	return this->networkKeys->toNodeIdentifier();
}

// src_blockchain/bc_network/NodeIdentifierSource.cpp
NodeIdentifier NodeIdentifierSource::toNodeIdentifier() const noexcept {
	const BigInteger* pubkey = this->pair->getPubKey();

	return NodeIdentifier(pubkey);
}
```


ちなみに[前々回の記事](/posts/staking-in-code/)で、投票プールを登録するときにも`NodeIdentifier`が出てきましたが、同じものです。

<!-- {{< tips title="テスト用パラメータに注意" color="sky" >}}
冒頭の`setupConfig02()`は、テストを短時間で回すために本番の既定値をいろいろ書き換えています。今回の話に関わるのは、ノードが張る接続の本数を**自分のゾーン2本・ほかのゾーン2本**にしているところです（本番の既定値は8本・4本）。3台しかいないテストなので、この本数でも全員とつながります。
{{< /tips >}} -->

## 1台目のノードを起動

準備が終わったので、1台目、`node01`の部分を見てゆきます。

```cpp
	ArrayNetworkSheeder seeder;    // 空の「シーダー」

	CodablecashNetworkNode node01(dirNode01, config01, &logger);
	{
		// First
		node01.setNodeName(L"node01");
		node01.generateNetwork(0, 1); // zone 0    // 最初のブロックを作る

		// after init
		node01.startNetwork(&seeder, false);       // 空のシーダーで起動

		node01.startMiner();
		node01.startStakePool();

		{
			uint16_t zone = 0;
			const NodeIdentifierSource* source = config01->getNetworkKey();
			NodeIdentifier nodeId = source->toNodeIdentifier();
			const wchar_t* host = L"::1";
			int port = config01->getPort();

			const UnicodeString* cname = config01->getCanonicalName();
			P2pNodeRecord* rec = P2pNodeRecord::createIpV6Record(zone, &nodeId, cname, host, port); __STP(rec);
			seeder.addRecord(rec);       // 1台目の連絡先をシーダーに入れる
		}
	}
```

まず`ArrayNetworkSheeder`という**空のシーダー**を用意しています。そしてこのシーダーは、**最初の連絡先を渡す**という役割を持っています。

名前（node01）をセットしたあとに、`generateNetwork()`でジェネシスブロック（マイニングで掘られたブロックではなく、ネットワークを始める人が最初に1つ置くブロック）を作ります。

そして、ノードが`startNetwork()`で起動。そのとき先ほどの空のシーダーを渡しています。続いてマイニング・ステーキングの機能が動き始めます。

<!-- 空のシーダーでします。最初のノードなので、誰も知らないのは当然ですね。起動したあとで、自分の連絡先（ゾーン・名札・ホスト・ポート）を`P2pNodeRecord`にまとめてシーダーに入れています。これで「とりあえずここに聞け」の1件目ができました。 -->

<!-- Bitcoinではシードの宛先がソフトに埋め込まれていますが、Codablecashの967b7ebの時点では、**シーダーに何を入れるかは呼び出し側に任されている**ことがここから分かります。この「1台目」の役が、テストネットでいう開発者さんのシードノードになるのだと思います。 -->

その後の`{}`で括った部分は、1台目のノードの情報（ゾーン、ノードID、このノードの正式名称`node_01`、ホスト、ポート）を取得して、空のシーダーに記入しています。

{{< tips title="node01とnode_01は別物" >}}
先ほど`setNodeName()`でセットした`node01`と、ここで出てくる正式名称`node_01`は別物です。前者はノードの内部で使う名前（ログやスレッド名用）、後者は`setCanonicalName()`でセットした、シーダーに載せて他のノードに見せる表示用の名前です。
{{< /tips >}}

このシードデータは、次に起動するノードに「とりあえずここに仲間がいるよ」という最初の連絡先を渡す役目となっているので、2台目がそれをどう使うかを見てみます。

## 2台目のノードを起動

ジェネシスブロックを生成した1台目のノードの次は、2台目のノードです。

ノードの名前をセットしてから`startNetwork()`を呼びます。1台目のときと比べると引数が少し違っていますね。第一引数のシーダーにはデータが入っていますし、第二引数も`true`になっています。

```cpp
	{
		config02->setPort(port02);
	}
	CodablecashNetworkNode node02(dirNode02, config02, &logger);
	{
		// second
		node02.initBlank(0, 1); // zone 0     // 空のデータフォルダを用意

		// after init
		node02.setNodeName(L"node02");
		node02.startNetwork(&seeder, true);  // 1台目のデータ入りシーダーで起動
		node02.syncNetwork();                // 仲間に追いつく

		// test commections
		{
			// node01
			{
				BlockchainNodeHandshake* hs01 = node01.getNodeHandshakeByNodeId(&nodeId01);
				StackHandshakeReleaser __releaser(hs01);
				CHECK(hs01 == nullptr);      // 1台目は、自分自身とはつながっていない
			}
			{
				BlockchainNodeHandshake* hs02 = node01.getNodeHandshakeByNodeId(&nodeId02);
				StackHandshakeReleaser __releaser(hs02);
				CHECK(hs02 != nullptr);      // 1台目から見て、2台目がつながっている
			}

			// node02
			{
				BlockchainNodeHandshake* hs01 = node02.getNodeHandshakeByNodeId(&nodeId01);
				StackHandshakeReleaser __releaser(hs01);
				CHECK(hs01 != nullptr);     // 2台目から見て、1台目がつながっている
			}
			// ・・・・・
		}

		// update seeder
		{
			// ・・・・・（1台目のときと同じ手順で、2台目の連絡先もシーダーに足す）
			seeder.addRecord(rec);
		}
	}
```

`node02.startNetwork(&seeder, true);`が何をしているかというと、以下のような感じです。

```cpp
// src_blockchain/bc_network_instance/CodablecashNetworkNode.cpp
void CodablecashNetworkNode::startNetwork(INetworkSeeder* seeder, bool pending) {
	// ・・・・・
	this->inst->startNetwork(host, port);    // 自分のポートで待ち受けを始める

	// start processors
	{
		const NodeIdentifierSource* networkKey = this->nwconfig->getNetworkKey();
		this->inst->startProcessors(networkKey, pending);  // 命令の処理担当を立ち上げる。pendingはここへ
	}

	// init database
	if(seeder != nullptr){
		ArrayList<P2pNodeRecord>* seedList = seeder->getSeedNodes(); __STP(seedList);   // シーダーの連絡先を取り出す
		// ・・・・・
		if(seedList != nullptr && !seedList->isEmpty()){
			initDatabase(seedList);    // 連絡先が1件でもあれば、それを元に台帳を作る
		}
	}

	// init connections
	maintainNetwork();   // 台帳から相手を選んでつなぐ
}
```

引数で渡したシーダー（`seeder`）の中の連絡先を`getSeedNodes()`で取り出し、データが1件でもあれば`initDatabase()`に渡します。
（1台目のときはシーダーが空だったのでここの処理はおこらない）

そしてシーダーに入っている1台目の連絡先をもとに`initDatabase()`が走り、続く`maintainNetwork()`でつなぎに行きます。

2つめの`true`と渡した引数、`pending`は、`startProcessors()`に渡されていました。コメントにも`// start processors`とあるように、ここで、届いた命令の処理担当（スレッド）を立ち上げているようです。

```cpp
// src_blockchain_p2p/bc_p2p_processor/P2pRequestProcessor.cpp
void P2pRequestProcessor::open(const NodeIdentifierSource *networkKey, CodablecashNodeInstance *inst, bool suspend) {
	// ・・・・・
	this->queueProcessor = new P2pRequestQueueProcessor(this->baseDir, this->p2pManager, this->transferProcessor, inst, this->logger);
	this->queueProcessor->open(suspend);  
	// ・・・・・
}
```

引数の名前が`pending`から`suspend`に変わっていますが同じ値を指しています。`suspend`が`true`だと、この担当を**立ち上げつつ止めておく**という意味でした（suspendの意味のとおり、吊るしておくということでしょうか）。
<!-- 、`true`だと**命令を処理する係を止めた状態で起こす**、という意味でした。2台目はまだ仲間に追いついていないので、追いつく前に仲間から流れてくる新着のブロックを処理し始めないように止めておく、と読めます。止めている間に届いた命令は捨てられず、溜めておかれます。 -->

そして、`node02.syncNetwork();`で仲間のノードに追いつく処理に移ります。

```cpp
// src_blockchain/bc_network_instance/CodablecashNetworkNode.cpp
void CodablecashNetworkNode::syncNetwork() {
	NetworkNodeSync sync(this);
	sync.sync(); 

	this->inst->resumeRequestProcessor(); 
}
```

最後の行の`resumeRequestProcessor()`が、さっき`true`で止めておいた担当を動かす合図です。「仲間に追いつくまでは新着を処理しない。追いついたら溜めていたぶんから処理を始める」という対になっているようです（resume：再開）。

<!-- ```cpp
// src_blockchain/bc_network_instance_sync/NetworkNodeSync.cpp
void NetworkNodeSync::sync() {
	// ・・・・・（同期用の一時フォルダを作り直す）

	// sync mempool at first
	UnicodeString memSyncThreadName(L"MemPoolSync");
	MemPoolSync memPoolSync(this, logger, &memSyncThreadName);
	memPoolSync.start();                                          // まず、まだブロックに入っていないトランザクションをもらう

	memPoolSync.join();                                           // 終わるまで待つ

	// sync blockchain or header
	uint16_t numZones = inst->getNumZones();
	this->zoneSelf = inst->getZoneSelf();

	for(int i = 0; i != numZones; ++i){
		AbstractZoneSync* zoneSync = AbstractZoneSync::createZone(i, zoneSelf, this, logger);
		this->zones->addElement(zoneSync);

		zoneSync->start();                                        // ゾーンごとに同期係を立てて、並行して走らせる
	}

	for(int i = 0; i != numZones; ++i){
		AbstractZoneSync* zoneSync = this->zones->get(i);

		zoneSync->join();                                         // 全ゾーンぶん終わるまで待つ
	}
}
``` -->

<!-- 順番は「まず未確定のトランザクション（メモリプール）をもらい、次にゾーンごとにブロックをもらう」でした。各ゾーンの同期係（`AbstractZoneSync`）がつながっている仲間の中から数台を選んでブロックをもらいに行く部分は、次回に回します。

そして`sync()`が全部終わったあと、`syncNetwork()`の最後の行で`resumeRequestProcessor()`を呼んでいます。これが、`startNetwork()`の`true`で止めておいた係を動かす合図です。「追いつくまでは新着を処理しない。追いついたら溜めていたぶんから処理を始める」という対になっていました。 -->


<!-- 2台目は`initBlank()`で空のデータフォルダを用意して、1台目の連絡先が入ったシーダーで`startNetwork()`します。`startNetwork()`の2つめの引数が1台目の`false`から`true`に変わっていますが、この意味は次回ソースを読むときに分かります。起動したら`syncNetwork()`で仲間に追いつきます。 -->

<!-- 注目したいのは、**`startNetwork()`と`syncNetwork()`の2つを呼んだだけで、次の行ではもう「つながっているか」を確かめている**ことです。相手を探す、接続する、名乗る、といった手順がここに見えないのは、全部`startNetwork()`の中で済んでいるからです。中で何をしているかは次回の宿題にします。 -->

テストコードからちょっと離れてしまいましたが、テストコード側であとに続いている`CHECK`が、このテストで確かめたい「期待値」です。

`getNodeHandshakeByNodeId(&nodeId01)`は、引数で渡したノードと今つながっているか？を返すもので、以下のように`node01`が`nodeId01`とつながっているか？というチェックの場合、同じノード同士を並べているので、**つながっていない**（`nullptr`＝相手がいなくて空）をチェックしています。

```cpp
	BlockchainNodeHandshake* hs01 = node01.getNodeHandshakeByNodeId(&nodeId01);
	StackHandshakeReleaser __releaser(hs01);
	CHECK(hs01 == nullptr);
```

- 1台目 → 1台目（自分とはつながらないので`nullptr`）
- 1台目 → 2台目（`nullptr`ではなく、つながっている）
- 2台目 → 1台目（`nullptr`ではなく、つながっている）
- 2台目 → 2台目（自分とはつながらないので`nullptr`）

## 3台目が加わる。そしてノード終了まで

最後に、3台目のノードが起動します。このコードの直前に2台目のノード情報をシーダーに加える処理が走るので、3台目の`startNetwork()`には、1台目・2台目の情報が入ったシーダーが渡ることになります。

```cpp
	{
		config03->setPort(port03);
	}
	CodablecashNetworkNode node03(dirNode03, config03, &logger);
	{
		// third
		node03.initBlank(0, 1); // zone 0

		// after init
		node03.setNodeName(L"node03");
		node03.startNetwork(&seeder, true);  // 1台目・2台目入りのシーダーで起動
		node03.syncNetwork();

		// test connections
		{
			// ・・・・・（3台×3台の9通りを全部確かめる。自分自身の3通りだけがnullptr）
			{
				BlockchainNodeHandshake* hs03 = node01.getNodeHandshakeByNodeId(&nodeId03);
				StackHandshakeReleaser __releaser(hs03);
				CHECK(hs03 != nullptr);                   // 1台目から見て、3台目がつながっている
			}
			// ・・・・・
		}
	}

	int maxHeight = 0;
	while(maxHeight < 5){
		Os::usleep(100000);
		maxHeight = node03.getMaxHeight(0);  // 3台目のブロックが高さ5になるまで待つ
	}

	node01.suspendMining();

	node03.shutdown();
	node02.shutdown();
	node01.shutdown();
}
```

ここでは、3台×3台の9通りを全部`CHECK`しています。自分自身とはつながらないから`nullptr`で、それ以外の6通りはつながっている、というテストです。

<!-- つまり3台全員が互いにつながった状態です。接続本数の上限はテストでは2本でしたから、3台目は1台目と2台目に1本ずつつないで、ちょうど上限いっぱいです。 -->

最後の`int maxHeight = 0;`からは、ノードではなくブロックの確認になっています。1台目のノードは`startMiner()`が走っているのでマイニングが動いています。その1台目が掘ったブロックが3台目までちゃんと届いて、ブロック高が5になるのを待っています。

それが確認できたら、1台目のマイニングを止めて、そのあと3台目から順に`shutdown()`で終了処理をしています。

<!-- ところで、この`shutdown()`は待ち受けをやめ、処理を止め、接続やファイルを閉じるだけで、**仲間に「やめます」と知らせてはいません**。知らせるほうは`broadCastShutdownCommand()`という別の関数で、同じフォルダの別のテスト（`test_sync_header_only.cpp`）が最後に呼んでいました。「やめます」を受け取った側が何をするかも、次回の宿題です。

## 台本から読めたこと

ここまでで「何が起きるか」が見えました。並べると、こうなります。

1. **ノードの名札は鍵から作る**。ランダムな番号ではなく、`NodeIdentifierSource`という鍵から`NodeIdentifier`を取り出す
2. **最初の相手は人間が教える**。シーダーに連絡先を入れるのは呼び出し側で、1台目は空のシーダーで起動する
3. **`startNetwork()`1回で、待ち受けから接続まで済む**。相手を探す・つなぐ・名乗る、はこの中にある
4. **接続は、つなぐ側と受ける側の両方に登録される**。つなぎに行っていない1台目からも、2台目が見える
5. **接続の本数には上限がある**。テストでは2本・2本、本番の既定値は8本・4本
6. **つながったら`syncNetwork()`で追いつく**。2台目以降が`startNetwork()`に`true`を渡していることと関係がありそう
7. **掘れたブロックは仲間の経路で届く**。1台目で掘ったものが、3台目で高さ5になる
8. **`shutdown()`は黙って止まる**。「やめます」を知らせるのは別の関数

## 次回への宿題

台本を読んで、逆に分からなくなったことも並べておきます。次回、ソースを読んで答える予定のものです。

- `startNetwork()`の中では、何がどういう順番で起きているのか
- シーダーに入っているのは1件か2件だけなのに、ノードはそれ以上の相手をどうやって知るのか。冒頭の投稿にあった「DNS」はここに関わるはず
- なぜ、つなぎに行っていない側（1台目）にも接続が登録されるのか。名乗りはどう確かめているのか
- 2台目以降が`startNetwork()`に渡している`true`は何か
- 「やめます」を受け取ったノードは何をするのか -->

## まとめ

今回は、テストコードからノードの流れを追いました。ソースコードよりもシンプルなので迷子になりにくいですし、どういう観点でテストしているのか？という部分も勉強になります。

次は、この流れの裏側を、ソースで追って見てゆこうと思います・・・！

<!-- 公開版で確かめたいこと(記事には載せない作業メモ)
- シードノードの指定方法(設定ファイル/CLI)。チェックリスト14
- 所属ゾーンの指定方法と初期ゾーン構成。チェックリスト16
- 本番のshutdown経路でbroadCastShutdownCommand()が呼ばれるか(967b7ebではテストが明示的に呼んでいる)
-->
