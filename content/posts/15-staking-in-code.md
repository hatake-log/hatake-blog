---
title: "Codablecashのソースコードで、ステーキングの中身を追いかけてみる"
slug: "staking-in-code"
date: 2026-09-23T11:45:00+09:00
draft: false
tags: ["暗号資産", "ステーキング", "Codablecash"]
cover:
  image: "images/staking-basics-top.png"
  alt: "Codablecashステーキングの仕組み"
---

[前回の記事](/posts/staking-basics/)で、ステーキングとは？という部分がちょっとは理解できたので、今度はコードベースでもっと具体的に理解していこうと思います。

題材とさせていただくのは、リリース間近の**Codablecash**です！

- [Codablecash開発者さんのアカウント](https://x.com/iizuka)
- [CodablecashのXアカウント](https://x.com/codablecash)
- [Codablecashのソースコード（GitHub）](https://github.com/alinous-core/codablecash)

コードはオープンソースなので、ステーキングが「中で何をしているのか」の実際のコードを追って確かめることができます。

前もってお知らせしておくと、私はPHPを少し触るくらいでC++の知識はありません。Codablecashのクラス名や短いコードを眺めながら「ふーむなるほど」と言いたい。というのが今回の趣旨なので、お気軽にお読みいただけると幸いです。

{{< tips >}}

Codablecashはリリース目前、つまり開発中プロジェクトなので、コードはこれからも変わる可能性があります。

とくに報酬の総量、PoWとPoSの配分、プール立ち上げ時のロックなどは今後変更の可能性が十分にありますので、細かい数値ではなく仕組み・流れを理解するという形で進めます。
{{< /tips >}}

記事内のコード引用は、[`967b7eb`](https://github.com/alinous-core/codablecash/tree/967b7eb4fc41c568a2c2b05cc63018b51e0d3fa5)（2026年9月8日）のコミットからお借りしています。

## ステーキングでやっていること

ステーキングに関連する部分を**チケット購入者の目線で**コードベースで追ったところ、大きく以下のような流れになっていました。

1. **チケット価格の決定**：256ブロックごとに`calcTicketPrice`が「合計ロック額 ➗ 理想の4万枚」で再計算する
2. **チケットの購入**：ウォレットが`RegisterTicketTransaction`を作る。投票先のノード・返却先アドレス・ロック額を`TicketUtxo`に書き込む
3. **購入の検証**：各ノードが`validateFinal`で「ロック額が現在価格以上か」「投票先のノードが（プール運営者によって）登録済みか」を確認する
4. **成熟待ち**：買ったチケットは256ブロックの間、抽選に出られない
5. **抽選**：ブロックごとに`TicketVoteSelector`が候補を集め、ブロック高のSHA-256を乱数表にして5枚を選ぶ
6. **投票**：選ばれた5枚のチケットが指名していた投票ノードが`VoteBlockTransaction`で投票する。5票そろうとブロックが確定
7. **報酬**：`BlockRewardCalculator`がマイナーと当選チケットで報酬を頭割り。各シェアの0.5%が投票ノードへの手数料、残りと元本がチケットの返却先アドレスへ
8. **ミスしたとき**：`RevokeMissedTicket`で元本は全額戻る。ただし投票ノードの台帳にミスが記録され、ミスが続くと抽選に出せる枠（`capacity`）が減る

## ステーキング関連のクラス

関連するコードの中心は、`src_blockchain/`配下の、名前に`finalizer`とつくディレクトリに集まっていました。

- `RegisterTicketTransaction` — チケットの登録（購入）
- `TicketUtxo` — チケット本体（ロックされたコイン）。ロック額・投票先ノード・返却先アドレスのデータを持つ
- `VoteTicket` — 投票ノード側に置いておくチケットの控え（買った高さなどの抽選に係る情報）
- `TicketVoteSelector` — 投票チケットの抽選
- `VoterEntry` — 投票ノードごとの台帳（抽選に出せる枠を管理）
- `VoteBlockTransaction` — ブロックへの投票
- `RevokeMissedTicket` — 投票ミスしたチケットの返金

このほか、別のディレクトリにある以下のクラスも登場します。

- `StatusCacheContext` — チケット価格の再計算
- `CodablecashSystemParam` — 各種パラメータの初期値
- `BlockRewardCalculator` / `BlockRewardStakeBase` — 報酬の計算

うーん、クラスだけでいっぱいありますね！さっそく見てゆきましょう。

## `StatusCacheContext` チケットの現在価格

まずはチケットの「現在価格」の定義から。CodablecashではDecredと同じく「買いたい人が多いと値上がりする自動調整」機能があるようで、それを担っている`calcTicketPrice()`という関数がありました。

関数内、冒頭の`height`・`window`・`mod`のコードは、チケット価格の再計算のタイミングについてで、「一定のブロック数ごとにしか再計算しない」という線引きがあるようです。

```cpp
// src_blockchain/bc_status_cache_context/StatusCacheContext.cpp
void StatusCacheContext::calcTicketPrice(const BlockHeader *header) {
	uint64_t height = header->getHeight();

	uint64_t window = this->config->getTicketPriceWindow(height);

	uint64_t mod = (height + 1) % window;
	if(mod != 0){
		return;
	}

	uint64_t numTicketMax = this->config->getTicketIdealNumber(height);
	uint64_t ticketPriceDefault = this->config->getTicketPriceDefault(height);

	// ・・・・・（全投票ノードの台帳を list に集める）

	BalanceUnit total(0L);                       // 合計を0から始める

	int maxLoop = list->size();
	for(int i = 0; i != maxLoop; ++i){           // 投票ノードを順に回って
		VoterEntry* entry = list->get(i);

		total += entry->getTicketPriceSum();     // そのノードが抱えるチケットのロック額の合計を足す
	}

	uint64_t price = total.getAmount() / numTicketMax;
	price = price < ticketPriceDefault ? ticketPriceDefault : price;

	this->ticketPrice = price;
}
```

- `numTicketMax` ：理想のチケット枚数
- `ticketPriceDefault` ：チケット価格の初期値・下限
- `total` ：現存するチケットの合計ロック額（全投票ノードの台帳を回って、各ノードが抱えるチケットのロック額を足したもの）

`price`を導く計算は、**合計ロック額 ➗ 理想のチケット枚数 = 新しいチケット価格**。`price`が下限より低ければ下限の値がセットされ、そうでなければ「新しいチケット価格」が採用される、という仕組みのようです。

また、パラメータ初期値のセットは以下に。

```cpp
// src_blockchain/bc/CodablecashSystemParam.cpp
CodablecashSystemParam::CodablecashSystemParam() {
	// ・・・・・

	this->ticketPriceDefault = 2;
	this->ticketPriceWindow = 256;
	this->ticketIdealNumber = 40000;

	// ・・・・・
}
```

チケット価格の下限は2、価格の再計算は256ブロックごと、理想のチケット枚数は40,000枚、となっていました。

## RegisterTicketTransaction （チケット購入）

次に、チケットの登録（＝購入）を担う、`RegisterTicketTransaction`を見てみます。ここではチケット購入の可否チェックをしているようです。

先に、出てくるワードについて。`ticketUtxo`の`UTXO`ですが、こちらは**Unspent Transaction Output**（取引で生まれて、まだ消費されていないコイン）の頭文字だそうです。`ticketUtxo`に関して言うと「チケットとしてロックされたコイン」を表しています。

<!-- この記事では、額面を自由に書き込めて、破って半分だけ使うことはできない「小切手」に例えます。使うときは丸ごと差し出し、お釣りは新しい小切手として切り直されます。

```
 手持ちの小切手A ─┐
 手持ちの小切手B ─┼─→  1枚のチケットを購入するための小切手1枚 (ticketUtxo)
 手持ちの小切手C ─┘    (+お釣りがあれば自分宛ての普通の小切手)
``` -->

```cpp
// src_blockchain/bc_finalizer_trx/RegisterTicketTransaction.cpp
TrxValidationResult RegisterTicketTransaction::validateFinal(
		const BlockHeader *header, MemPoolTransaction *memTrx, IStatusCacheContext *context) const {
	{
		uint64_t priceUint = context->getTicketPrice();
		BalanceUnit price(priceUint);
		BalanceUnit amount = this->ticketUtxo->getAmount();
		if(price.compareTo(&amount) > 0){
			return TrxValidationResult::INVALID;
		}
	}

	・・・・・
}
```

- `priceUint`：今この時点でチケット1枚を買うのに必要な最低額（前述の`calcTicketPrice`で決まる値）
- `amount`：`this->ticketUtxo->getAmount()`。このチケットにロックしようとしている額
- `if(price.compareTo(&amount) > 0)`：条件チェック。チケット価格が、ロックしようとしている額より大きいなら（つまり、コインがチケット価格に満たないなら）

チケット価格（priceUint）とロック用に差し出した額(amount)を比較して、条件によって「無効」を返す、ということをしています。

`price.compareTo(&amount)`自体は0、1、-1、のいずれかを返すので、それを` > 0`かどうかで分岐しています。

簡単に言うと、「コインがチケット価格に足りていないならNOを返す」役割の関数ですね。

### `TicketUtxo`

`TicketUtxo`というクラスの定義も見てみましょう。チケット（ロックされたコインそのもの）本体のクラスです。

```cpp
// src_blockchain/bc_finalizer_trx/TicketUtxo.h
class TicketUtxo: public AbstractUtxo {
	// ・・・・・

	virtual BalanceUnit getAmount() const noexcept;

	//・・・・・

private:
	NodeIdentifier* nodeId; // Stake pool
	AddressDescriptor* addressDesc; // registered ticket returned address
	BalanceUnit amount;
};
```

定義されている変数です。

- nodeId：投票を任せるノード（コメントにStake poolとあります）
- addressDesc：元本を返してもらう先のアドレス
- amount：ロックする額

チケットを購入するとき、同時にプールも指定しますよね。それらの情報もチケットに記録されているのですね。

<!-- またさきほどの検証コードで呼ばれていた`this->ticketUtxo->getAmount()`は、この`amount`をそのまま返すだけの関数になっていました。

```cpp
BalanceUnit TicketUtxo::getAmount() const noexcept {
	return this->amount;
}
```
（TicketUtxo.cpp#L109-L111） -->

この変数に実際に値が入るのはどこかというと、`RegisterTicketTransaction`自身は空の`TicketUtxo`をnewし、それぞれのセッターが用意されていました。

```cpp
// src_blockchain/bc_finalizer_trx/RegisterTicketTransaction.cpp
RegisterTicketTransaction::RegisterTicketTransaction() : AbstractFinalizerTransaction() {
	this->ticketUtxo = new TicketUtxo();
}

// ・・・・・

void RegisterTicketTransaction::setNodeId(const NodeIdentifier *nodeId) noexcept {
	this->ticketUtxo->setNodeIndentifier(nodeId);
}

void RegisterTicketTransaction::setAddressDescriptor(const AddressDescriptor *ticketReturnaddressDesc) noexcept {
	this->ticketUtxo->setAddressDescriptor(ticketReturnaddressDesc);
}

void RegisterTicketTransaction::setAmounst(BalanceUnit amount) noexcept {
	this->ticketUtxo->setAmounst(amount);
}
```

そして、そのセッターを呼んでいるのは、ノードではなく**ウォレット側**でした。ウォレットの「チケットを買う」処理（`RegisterTicketTransactionWalletHandler::createTransaction`）が、投票先のノードID・ロック額・返却先アドレスを引数で受け取り、トランザクションを組み立てて署名、という流れのようです。

```cpp
// src_blockchain/bc_wallet_trx/RegisterTicketTransactionWalletHandler.cpp
RegisterTicketTransaction* RegisterTicketTransactionWalletHandler::createTransaction(const NodeIdentifier *nodeId, const BalanceUnit& stakeAmount,
		const BalanceUnit& feeRate, const AddressDescriptor *ticketReturnaddressDesc, const IWalletDataEncoder *encoder, ITransactionBuilderContext *context) {
	// ・・・・・

	RegisterTicketTransaction* trx = new RegisterTicketTransaction(); __STP(trx);
	trx->setNodeId(nodeId);  // 投票ノードのid
	trx->setAddressDescriptor(ticketReturnaddressDesc);
	trx->setAmounst(stakeAmount);

	trx->build();
	trx->sign(musigProvidor, &utxoFinder);

	// ・・・・・

	return __STP_MV(trx);
}
```

つまり「いくらロックするか」「どのノードに任せるか」を決定するのはウォレットで、ノード側はさきほどの`validateFinal`で「その額が現在価格以上か」「任せる先のノードが登録済みか」を検査する、という分担になっているようです。

<!-- ネットワーク越しにこのトランザクションを受け取った他のノードは、`fromBinary`でバイト列から同じ`TicketUtxo`を復元して同じ検査をします（同#L115-L123）。なお`setAmounst`は綴りが揺れていますが、原文のままです。 -->

<!-- ### 親クラスの`AbstractUtxo`

`TicketUtxo`の親クラスである`AbstractUtxo`についても見てみます。

「UTXOを名乗るクラスは**必ず自分の額を答えられること**」を約束事として宣言しておりAbstractUtxo.h#L43の`virtual BalanceUnit getAmount() const noexcept = 0;`）、`TicketUtxo`はそれを継承して自クラスで実装している、という関係のようです。 -->

### チケットの成熟期

チケットが買えてもすぐに抽選に出られるわけではありません。パラメータの初期値に、こんな2行がありました。Matureとは"成熟"という意味です。

```cpp
// src_blockchain/bc/CodablecashSystemParam.cpp
CodablecashSystemParam::CodablecashSystemParam() {
	// ・・・・・
	this->ticketMatureIntervalHeight = 256;
	this->ticketExpireHeight = 20 * 24 * 30 * 3;
	// ・・・・・
}
```

まず`ticketMatureIntervalHeight = 256`について。買ったチケットが**抽選の対象になるまで256ブロック待つ**という成熟期間のようです。Decredでも、買った直後のチケットはimmature（未成熟）と表示され、すぐには投票に参加できないですよね。あれと同じ概念のようです。

この256は、抽選の候補を集める`makeList()`で「成熟の境界線」として使われていました。

```cpp
// src_blockchain/bc_finalizer/TicketVoteSelector.cpp
void TicketVoteSelector::makeList() {
	// ・・・・・
	uint64_t matureHeight = this->height - this->tiketMatureIntervalHeight;  // 今のブロック高 − 256
	// ・・・・・
			const VoteTicket* ticket = entry->nextTicket(matureHeight);  // 成熟期を過ぎたチケットの中から1枚出して
	// ・・・・・
}
```

<!-- この境界線より後に買われたチケットは候補に入りません（実際に足切りしているコードは、後の「抽選候補について」で出てきます）。 -->

そして、`ticketExpireHeight`は20×24×30×3＝43,200ブロック。チケットの失効に関する値？と思ったら、購入から一定のブロック数が過ぎても当選しないままのチケットを**高優先リストに入れる**ための基準値でした！

```cpp
// src_blockchain/bc_finalizer/TicketVoteSelector.cpp
void TicketVoteSelector::addList(const VoteTicket *ticket) {
	uint64_t ticketHeight = ticket->getHeight();       // このチケットを買ったブロック高
	uint64_t expire = this->height - ticketHeight;    // 買ってから何ブロックたったか

	if(expire < this->ticketExpireHeight){            // 43,200ブロック未満なら
		this->candidateList->addElement(ticket);      // 通常の候補リストへ
	}
	else{
		this->expiredList->addElement(ticket);        // 超えていたら優先リストへ
	}
}
```

長く待たされたチケット（43,200ブロックは3分間隔で約90日）を優先して救済する仕組みのようです。そんな親切設計があるのですね。

## `TicketVoteSelector` チケット投票権を得る流れ

さて、チケット価格が決まり、チケット購入まで進みました。成熟期をすぎたら投票に参加できる土台は十分です。

まず、投票の前提ですが、**ブロックごとの投票に使われるチケットは5枚まで**です。

先ほど、理想のチケット枚数（ticketIdealNumber）は4万枚、とコードから見つけました。つまり4万枚ほどあるチケットのうち、各投票ノードが差し出した候補の中から、ブロックの投票権を得る「たった5枚」を選ぶ必要があります。

その5枚を選ぶ（抽選する）役割を担うのが、この`TicketVoteSelector`クラスのようです。

<!-- 出てくるワードの確認から。

- コインをロックしてチケットを買った人が**チケット保有者**
- 「投票を任せる先」として指名したノードが**投票ノード**（自分でノードを立てたり、他の人が運営するプールのノードだったり） -->

<!-- では、どのチケットが抽選に当たって投票権を得るのでしょう。抽選で選ばれるのはあくまでチケットで、当選したチケットの代わりに実際の投票操作をするのが投票ノード、という役割分担になっています。 -->

### `makebuffer()`　抽選用の乱数表を作る

`TicketVoteSelector`クラスに、この抽選用の**乱数表**を作る`makebuffer()`という関数がありました。

```cpp
// src_blockchain/bc_finalizer/TicketVoteSelector.cpp
ByteBuffer* TicketVoteSelector::makebuffer() {
	ByteBuffer* buff = ByteBuffer::allocateWithEndian(sizeof(uint64_t), true); __STP(buff);
	buff->putLong(this->height);   // 「何番目のブロックか」という数字を、8マスの箱に左から詰める。書き終わるとペン先は箱の右端にいる
	buff->position(0);             // ペン先を箱の左端に戻す。次に箱を読む人が最初から読めるように

	// Sha
	ByteBuffer* shabuff = Sha256::sha256(buff, true); __STP(shabuff);
	shabuff->put((char)0);
	shabuff->position(0);

	return __STP_MV(shabuff);
}
```

ここでは`sha256`という関数が使われています。`sha256`は「バイトの並び」を受け取る関数なので、`sha256`に渡すために**ブロックの高さを8バイトに整形する**、という作業を行なっています。その作業に該当するのが`ByteBuffer`〜`buff->position(0)`のくだりで、ちょっと難しいですが以下に簡単にメモをしておきます。

- `ByteBuffer`：バッファ（数字をバイトの並びに直すための、一時的な作業スペース）
- `this->height`：今から処理するブロックの高さ（何番目のブロックか）
- `sizeof(uint64_t)`：ブロック高を入れる型の大きさ＝8（作業スペースを8バイトで借りる指定）
- `buff->putLong()`：ブロック高の数値を8バイトに直して、作業スペースに書き込む（書いた分だけペン先が右へ進む）
- `buff->position(0)`：ペン先を左端に戻す（次のSHA-256が先頭から読めるように）

このような事務的？な作業を経て作成されるのが、`shabuff`です。

`shabuff = Sha256::sha256(buff, true)` **ブロックの高さをSHA-256でハッシュした32バイト**の乱数表を手に入れました。ここまではまだ乱数表を作っただけで、抽選は行われていませんね。

では、その乱数表からどうやってチケットを選ぶのかというと、同じクラスに`doSelect()`と、`selectFromList()`という関数がありました。2つの関数は以下のような関係になっています。

- `selectFromList()`：実際に抽選を行う関数
- `doSelect()`：必要な回数だけ`selectFromList()`を呼び出す

### `doSelect()` 抽選の土台

`doSelect()`から見てみましょう。count = 0 から始まって、まず優先組から`expCount`回、続けて通常組から`candidateCount`回（合計で最大5回）`selectFromList()`を呼んでいます。

前半で、`expCount`・`candidateCount`を定義していますね。

```cpp
// src_blockchain/bc_finalizer/TicketVoteSelector.cpp
void TicketVoteSelector::doSelect() {
	// high priority
	int expCount = this->expiredList->size();
	expCount = expCount >= this->votePerBlock ? this->votePerBlock : expCount;

	// normal priority
	int candidateCount = this->votePerBlock - expCount;
	candidateCount = candidateCount > this->candidateList->size() ? this->candidateList->size() : candidateCount;

	ByteBuffer* shabuff = makebuffer(); __STP(shabuff);   // さきほどの「抽選用の乱数表」を作る

	int count = 0;                                          // 何枚目を選んでいるか。0から始まる
	for(int i = 0; i != expCount; ++i){
		const VoteTicket* ticket = selectFromList(this->expiredList, count, shabuff);   // 長く待たされたチケットから先に選ぶ
		this->selected->addElement(ticket);
		count++;                                            // 1枚選ぶたびに1増える
	}

	for(int i = 0; i != candidateCount; ++i){
		const VoteTicket* ticket = selectFromList(this->candidateList, count, shabuff); // 残りの枠を通常の候補から選ぶ
		this->selected->addElement(ticket);
		count++;
	}

}
```

- `votePerBlock`：1ブロックで選ぶ枚数（初期値5）
- `expiredList`：長く待たされて優先扱いになったチケットのリスト。ここから先に、最大5枚まで選ぶ
- `candidateList`：通常の候補のリスト。優先組で埋まらなかった残りの枠をここから選ぶ
- `count`：何枚目の抽選かを数える通し番号（0〜4）。優先組と通常組で通しで数え、`selectFromList()`に渡して「乱数表のどこを読むか」をずらすのに使う

「1ブロックで選ぶ枚数」`votePerBlock`の初期値は5で、ここでセットされていました。

```cpp
// src_blockchain/bc/CodablecashSystemParam.cpp
CodablecashSystemParam::CodablecashSystemParam() {
	// ・・・・・
	this->votePerBlock = 5;
	// ・・・・・
}
```

### `selectFromList()` 抽選本体

そして、抽選の本体である`selectFromList()`です。`doSelect()`からは以下の2パターンで呼ばれていましたね。

- `selectFromList(this->expiredList, count, shabuff)` 
- `selectFromList(this->candidateList, count, shabuff)` 

```cpp
// src_blockchain/bc_finalizer/TicketVoteSelector.cpp
const VoteTicket* TicketVoteSelector::selectFromList(ArrayList<const VoteTicket> *list, int count, ByteBuffer* shabuff) {
	uint16_t pos = count % 32;
	pos = shabuff->getShort(pos);   // 乱数表のcountバイト目から2バイトを、数字として読む

	// ・・・・・

	pos = pos % list->size();       // 候補の枚数で割った余り＝「何番目のチケットか」

	return list->remove(pos);       // そのチケットを当選として抜き取る
}
```

- `pos`：乱数表の何バイト目から読むかを定義し、それを2バイトの数値化し、当たりチケットの番号を保有、という段階による役割を持つ
- `list->size()`： 候補リストに今入っているチケットの枚数

32バイトの乱数表（`shabuff`）の`count`バイト目から2バイトを数字として読み、「候補の枚数で割った余り」の番号のチケットを、当たったチケットとして抜いています。

ここで大事なのは、**この計算に出てくるのが「乱数表」と「候補の枚数」だけ**という点です。チケットにいくらロックしたかは、式のどこにも出てきません。つまり選ばれ方はチケット1枚ごとの平等な抽選で、「たくさんロックした人ほど1枚あたりの当選確率が上がる」ような重み付けは見当たりませんでした。確率を上げたければチケットを複数枚買う、という素直な設計のようです。

### 抽選候補について

チケットの中から選ばれる候補のリストは、各投票ノードが自分の抱えるチケットを先頭から順に差し出して作るのですが、その差し出す側の関数にこうありました。

```cpp
// src_blockchain/bc_finalizer/VoterEntry.cpp
const VoteTicket* VoterEntry::nextTicket(uint64_t matureHeight) noexcept {
	int size = this->list->size();
	size = size >= this->capacity ? this->capacity : size;   // 出せるのはcapacity枚まで

	if(this->pos >= size || this->list->get(this->pos)->getHeight() > matureHeight){
		return nullptr;   // 上限に達した、または次のチケットがまだ成熟していない
	}

	return this->list->get(this->pos++);
}
```

1回の抽選に出せる枚数には、投票ノードごとの上限（`capacity`）があり、この上限の範囲内で、成熟前のチケットは除外したものを候補として出しているようです。

### 5票そろうとブロックが確定

ここまでで、1ブロックにつき5枚のチケットが選ばれ、それぞれの投票ノードが投票するところまで来ました。集まった票が`votePerBlock`に達したかを判定しているのがこちらです。

```cpp
// src_blockchain/bc_block/BlockHeader.cpp
bool BlockHeader::isFinalizing(int votePerBlock) const noexcept {
	const VotedHeaderIdGroup* group = this->votePart->getMaxVotedGroup();

	return group != nullptr && group->size() == votePerBlock;
}
```

こうして1ブロックごとの投票が規定数に達すると、ブロックは確定作業へと進みます。

## `BlockRewardCalculator` 報酬を計算する

やっとここまで来ました。嬉しい報酬関連です。

`BlockRewardCalculator`クラスの`calcRewords()`を見てみます。

```cpp
// src_blockchain/bc_block_generator/BlockRewardCalculator.cpp
void BlockRewardCalculator::calcRewords(uint64_t height, uint16_t zone) noexcept {
	BalanceUnit total = getTotalRewords4Shards(height, zone) + this->fee;

	int totalShare = this->list.size();
	if(this->pow != nullptr){
		totalShare++;
	}

	if(totalShare == 0){
		return;
	}

	BalanceUnit perShare = total / totalShare;
	BalanceUnit remain = total - (perShare * BalanceUnit(totalShare));

	int maxLoop = this->list.size();
	for(int i = 0; i != maxLoop; ++i){
		BlockRewardStakeBase* stake = this->list.get(i);
		stake->setReward(perShare);
	}

	if(this->pow != nullptr){
		BalanceUnit powShare = perShare + remain;
		this->pow->setReward(powShare);
	}

}
```

- `total`： このブロックで配る総額。（直前の行で「ブロック報酬 + 手数料」として計算）
- `this->list`： このブロックに取り込まれた投票チケットのリスト（0〜5枚）
- `this->pow`： このブロックを掘ったマイナーの報酬の受け皿（受取アドレスが設定されていれば作られる。なければnullptr＝空）

報酬総額を「投票の数＋PoWマイナー1」で割っています。つまり最大6等分ですね。

計算で割り切れなかった端数（`remain`）に関しては、`BalanceUnit powShare = perShare + remain;`の箇所で、マイナーに乗せられます。

### `BlockRewardStakeBase` ステーキング手数料

`calcRewords()`では、ブロック報酬をマイナー1人と当選したチケット各1枚に、`perShare`ずつ配られるということがわかりました。

でも、当選チケット1枚には2人の関係者がいましたね。

- チケット保有者：コインをロックしてチケットを買った人
- 投票ノード：そのチケットが指名した、実際に投票するノード（プール運営者のノード。自前で立てるなら保有者本人のノード）

この2人に対してどのように報酬が分けられるかは、以下の`calcTicketOwnerBalance()`で計算されていました。

```cpp
// src_blockchain/bc_block_generator/BlockRewardStakeBase.cpp
BalanceUnit BlockRewardStakeBase::calcTicketOwnerBalance(uint64_t ticketVoterFeeBasisPoint) const {
	BalanceUnit voterReword = this->reward * BalanceUnit(ticketVoterFeeBasisPoint) / 10000L;
	BalanceUnit ticketReword = this->reward - voterReword;

	BalanceUnit amount = ticketReword + this->ticketVotedUtxo->getAmount();

	return amount;
}
```

`ticketVoterFeeBasisPoint`は、以下で初期値が50にセットされていました。

```cpp
// src_blockchain/bc/CodablecashSystemParam.cpp
CodablecashSystemParam::CodablecashSystemParam() {
	// ・・・・・

	this->ticketVoterFeeBasisPoint = 50;

	// ・・・・・
}
```

つまり、報酬の内訳は以下です。

- `voterReword = this->reward * BalanceUnit(ticketVoterFeeBasisPoint) / 10000L`　：0.5%。投票を実行した側（プールやノード）
- `ticketReword = this->reward - voterReword`　：残り99.5%がチケット所有者へ（チケット元本とともに）

この計算をもとに、当選して投票が済んだチケット1枚ごとに「**投票済みチケットの精算**」の取引が1本、ブロックに載ります（exportStakeBaseTransaction）。入力は投票済みチケットの小切手、出力は「元本＋報酬の99.5%」をチケットの返却先へ、「報酬の0.5%」を投票ノードのアドレスへ、の2枚です。プール運営者が委任者の元本に触る場面はなく、精算はプロトコルが自動で振り分けます。

## `RevokeMissedTicket` 投票ミスしたチケットの返金

投票をミスしたチケットの扱いを見てみます。

投票しそこねたチケットは、ロックしていた額がそのまま元のアドレスに払い戻されるようです。この取り消しのトランザクションを組み立てているのは、`BlockGenerator`クラスの`addRevokeMissedTicket()`でした。

```cpp
// src_blockchain/bc_block_generator/BlockGenerator.cpp
void BlockGenerator::addRevokeMissedTicket(・・・・・, VoteCandidate *candidate) {
	RevokeMissedTicket* revokeTrx = new RevokeMissedTicket(); __STP(revokeTrx);

	// ・・・・・

	BalanceUnit ticketPrice = candidate->getTicletPrice();              // ロックしていた額
	const AddressDescriptor* desc = candidate->getAddressDescriptor();   // チケットに書いた返却先

	BalanceUtxo utxo(ticketPrice);
	utxo.setAddress(desc);
	revokeTrx->addBalanceUtxo(&utxo);   // 出力: 同じ額を、返却先宛ての普通の小切手として

	// ・・・・・

	block->addControlTransaction(revokeTrx);   // ブロックに載せる
}
```

引数で渡される`candidate`は、取り消し対象である「当選したのに投票が届かなかったチケット」です。そのチケットのロック額、返却先アドレス宛てに返金する、という処理を行っています。

### `VoterEntry` ミスのペナルティ

「投票ミスによるペナルティ」と聞くと、コインをロックしてチケットを買った人はどきっとしてしまうかもしれませんが、実際に投票するのは投票ノードです。

そのため、ミスによるペナルティは投票ノードに課せられます（個人でノードを立てている場合も同様）。チケット保有者の側は、その回の報酬をもらえないだけで、元本は前の節のとおり返金されます。

そして、その処理を担う`VoterEntry`にこんな関数がありました。

```cpp
// src_blockchain/bc_finalizer/VoterEntry.cpp
void VoterEntry::handleMissed(int missingLimit) noexcept {
	this->extendCount = 0;

	this->missingCount++;
	if(this->missingCount >= missingLimit){
		this->capacity = this->capacity / 2;
		this->missingCount = 0;
	}

	this->updated = true;
}
```

`voteMissingLimit`の初期値は2にセットされています。

```cpp
// src_blockchain/bc/CodablecashSystemParam.cpp
CodablecashSystemParam::CodablecashSystemParam() {
	// ・・・・・

	this->voteMissingLimit = 2;

	// ・・・・・
}
```

その投票ノードが抽選に出せるチケット枠の上限を、`capacity`が持っています。ミスが連続して`missingLimit`（初期値2）に達すると、`this->capacity / 2`で**上限が半分に**減ってしまうようです。
（逆に、投票を成功させ続けると枠が1つ増える`handleVoted`という関数もありました）

投票ミス自体はコイン喪失などのペナルティとはならない代わりに、**信用スコアが下がって参加枠を減らされる**という仕組みでした。これはステーキングプールを運営する人にとっては要注意ポイントですね。

## 終わりに

追いきれていない部分もかなりあると思いますが、主だったコードを実際に見ることでぼや〜としていたステーキングへの理解が少し深まりました。

またメインネットができるころにはこの記事の内容を見返して、本番で変更された点なども確認しますね。