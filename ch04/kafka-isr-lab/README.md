# kafka-isr-lab

가상 면접 2권 4장(분산 메시지 큐)의 복제, 사본 동기화(ISR), ACK 설정을 로컬 카프카 클러스터로 직접 확인하는 실습이다. 책 139~145쪽과 스터디 정리 `ch04/정리.md`를 같이 본다.

## 구성

```
컨트롤러 3대 (KRaft, 과반수로 메타데이터 합의)      = 교무실 선생님 3명
  controller-1 (id 1)  controller-2 (id 2)  controller-3 (id 3)

브로커 3대 (데이터 파티션을 ISR로 복제)            = 김, 이, 박 선생님
  broker-1 (id 11)     broker-2 (id 12)     broker-3 (id 13)

tools: 명령만 실행하는 컨테이너. 브로커를 꺼도 명령을 칠 수 있다
```

- 이미지는 `apache/kafka:4.1.0`, 메모리는 2GB 안팎을 쓴다. 호스트로 여는 포트는 없다.
- `describe` 결과의 `Leader`, `Replicas`, `Isr`에 나오는 숫자는 브로커 id다(11 = broker-1).
- `./k <도구> [인자]`는 tools 컨테이너에서 `kafka-<도구>.sh`를 브로커 주소와 함께 실행한다.

## 0. 띄우기

```bash
docker compose up -d
./k metadata-quorum describe --status
```

`LeaderId`가 리더 컨트롤러다. `CurrentVoters`는 투표하는 컨트롤러 1, 2, 3이고, `CurrentObservers`는 메타데이터 로그만 따라 읽는 브로커 11, 12, 13이다.

토픽을 만든다. 사본 3개, 최소 ISR 2개다.

```bash
./k topics --create --topic orders --partitions 3 --replication-factor 3 --config min.insync.replicas=2
./k topics --describe --topic orders
```

```
Partition: 0  Leader: 13  Replicas: 13,11,12  Isr: 13,11,12
Partition: 1  Leader: 11  Replicas: 11,12,13  Isr: 11,12,13
Partition: 2  Leader: 12  Replicas: 12,13,11  Isr: 12,13,11
```

메시지는 이렇게 보내고 읽는다. 대화형으로 보내려면 `echo ... |` 없이 실행하고, 줄마다 입력한 뒤 Ctrl+D로 끝낸다.

```bash
echo "주문-1" | ./k console-producer --topic orders --producer-property acks=all
./k console-consumer --topic orders --from-beginning --timeout-ms 5000
```

## 실험 1. 브로커 하나가 꺼지면 ISR이 줄고, 쓰기는 계속된다

```bash
docker compose stop broker-3
./k topics --describe --topic orders
echo "주문-2" | ./k console-producer --topic orders --producer-property acks=all
```

```
Partition: 0  Leader: 11  Replicas: 13,11,12  Isr: 11,12
Partition: 1  Leader: 11  Replicas: 11,12,13  Isr: 11,12
Partition: 2  Leader: 12  Replicas: 12,13,11  Isr: 12,11
```

- `Replicas`(사본을 둘 곳)는 그대로 셋이고, `Isr`(따라잡은 사본 명단)만 둘로 줄었다.
- 파티션 0은 리더가 13이었는데 11로 바뀌었다. 컨트롤러가 ISR에서 새 리더를 뽑았다.
- 명단이 2개라 `min.insync.replicas=2`를 만족하므로 `acks=all` 쓰기가 성공한다.

## 실험 2. 하나 더 꺼지면 acks=all은 거부되고 acks=1은 된다

```bash
docker compose stop broker-2
./k topics --describe --topic orders

# 재시도를 짧게 줘서 2분 대신 8초 만에 결과를 본다
echo "주문-3" | ./k console-producer --topic orders --producer-property acks=all \
  --producer-property request.timeout.ms=3000 --producer-property delivery.timeout.ms=8000
echo "주문-4" | ./k console-producer --topic orders --producer-property acks=1
```

```
Partition: 0  Leader: 11  Replicas: 13,11,12  Isr: 11  Elr: 12

... retrying (2 attempts left). Error: NOT_ENOUGH_REPLICAS
ERROR Error when sending message to topic orders ...
NotEnoughReplicasException: Messages are rejected since there are fewer in-sync replicas than required.
```

- 명단에 리더(11) 하나만 남아 `acks=all` 쓰기를 리더도 디스크에 쓰지 않고 거부한다. 생산자는 재시도하다가 시간이 다 되면 오류를 받는다.
- `acks=1`은 최소 ISR을 보지 않으므로 리더 하나에 쓰고 성공한다. 지금 리더가 죽으면 이 메시지는 사라진다.
- `Elr: 12`는 카프카 4.x의 ELR(*Eligible Leader Replicas*, KIP-966)이다. ISR이 최소값 밑으로 줄 때 명단에서 빠진 사본 가운데, 확정된 메시지까지는 가지고 있는 사본을 "리더가 돼도 되는 후보"로 따로 기억한다. broker-3은 ISR이 아직 2개일 때 빠져서 후보에 없다.

되살리고 읽어 본다.

```bash
docker compose start broker-2 broker-3
./k topics --describe --topic orders
./k console-consumer --topic orders --from-beginning --timeout-ms 5000
```

- 몇 초 안에 `Isr`이 셋으로 돌아온다. 돌아온 브로커가 리더를 따라잡으면 명단에 다시 들어간다.
- 리더는 한동안 11에 몰려 있다. 5분(`leader.imbalance.check.interval.seconds`)마다 `Replicas`의 첫 번째 브로커로 리더를 되돌린다.
- 소비자 출력에 거부된 "주문-3"은 없다.

## 실험 3. 명단 안의 사본이 멈추면 acks=all이 그 사본을 기다린다

`pause`는 컨테이너를 끄지 않고 얼린다. 명단에 남아 있는데 응답이 없는 사본을 흉내 낸다.

```bash
time (echo "주문-5" | ./k console-producer --topic orders --producer-property acks=all)   # 평소
docker compose pause broker-3
time (echo "주문-6" | ./k console-producer --topic orders --producer-property acks=all)   # 얼린 직후
time (echo "주문-7" | ./k console-producer --topic orders --producer-property acks=all)   # 명단에서 빠진 뒤
docker compose unpause broker-3
```

실제로 잰 값은 2초, 8초, 1초였다(콘솔 생산자는 JVM이 뜨는 데만 1~2초가 걸린다).

- 얼린 직후에는 리더가 명단에 있는 broker-3까지 기다리느라 늦어진다. 과반수 방식이었다면 나머지 둘이 받는 즉시 대답했을 것이다.
- 얼린 브로커는 하트비트도 못 보내서 9초(`broker.session.timeout.ms`) 뒤 컨트롤러가 펜싱(쓰지 못하게 막음)하고 명단에서 뺀다. 그 뒤로는 다시 빨라진다.
- 하트비트는 보내는데 따라 베끼기만 느린 사본이면 30초(`replica.lag.time.max.ms`)를 기다린 뒤 명단에서 빠진다.

## 실험 4. 컨트롤러는 과반수로 정한다

```bash
./k metadata-quorum describe --status          # LeaderId 확인 (예: 3)
docker compose stop controller-3               # 리더를 끔
./k metadata-quorum describe --status          # 남은 둘 가운데 새 리더가 뽑힘
docker compose stop controller-1               # 하나 더 끔 -> 1대만 남아 과반수(2)를 못 채움
```

1대만 남은 상태에서 두 가지를 해 본다.

```bash
echo "주문-8" | ./k console-producer --topic orders --producer-property acks=all   # 된다
./k topics --create --topic refunds --partitions 1 --replication-factor 3          # 끝나지 않는다 (Ctrl+C)
```

- 이미 있는 파티션에 쓰고 읽는 일(데이터)은 브로커끼리 ISR로 하므로 계속된다.
- 토픽 생성처럼 메타데이터를 바꾸는 일은 컨트롤러 과반수가 받아 적어야 확정되므로 멈춘다. `metadata-quorum describe`도 응답하지 않는다.
- 데이터는 ISR(명단 전부), 메타데이터는 과반수라는 차이가 여기서 보인다.

```bash
docker compose start controller-1 controller-3
```

## 정리

```bash
docker compose down -v
```

## 학교 비유로 보면

| 여기 | 카프카 이름 | 비유 |
|---|---|---|
| controller-1~3 | 컨트롤러 (KRaft) | 교무실 선생님 3명. 장부를 2명 이상이 받아 적으면 확정 |
| broker-1~3 | 브로커 | 김, 이, 박 선생님. 책장에 권(파티션)을 보관 |
| `orders` | 토픽 | 주문책 |
| Partition 0~2 | 파티션 | 주문책 0~2권 |
| Leader | 리더 | 원본을 가진 선생님 |
| Isr | ISR | 원본을 다 따라 베낀 선생님 명단 |
| `acks=all` | ACK | 명단의 선생님이 모두 베낀 뒤에 작가에게 "받았어요" |
| `min.insync.replicas=2` | 최소 ISR | 두 명 이상 가지고 있지 않으면 원고를 안 받는다 |
