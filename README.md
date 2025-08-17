# Constelize – ARC Program Synthesis Experiments

Constelize is a symbolic program synthesis system designed to solve ARC tasks by extracting facts from inputs, mapping them into symbolic actions, and composing them into procedures.

---

## ⚙️ Setup

1. **Create the database**  
   Run the utility script to generate the SQLite database:

   ```bash
   python db/utils.py

1. **Verify completed tasks**  
   Once the database is ready, run the verification script:
   ```bash
   python scripts/verify_done_tasks.py
   
3. **Current result for 63 tests**

```code
0b148d64.json: SUCCESS in 11.44 seconds
1cf80156.json: SUCCESS in 8.31 seconds
1f85a75f.json: SUCCESS in 18.68 seconds
23b5c85d.json: SUCCESS in 9.17 seconds
25ff71a9.json: SUCCESS in 10.86 seconds
28bf18c6.json: SUCCESS in 11.20 seconds
2dc579da.json: SUCCESS in 9.56 seconds
2dee498d.json: SUCCESS in 7.80 seconds
32597951.json: SUCCESS in 21.05 seconds
3618c87e.json: SUCCESS in 9.39 seconds
3aa6fb7a.json: SUCCESS in 7.95 seconds
3af2c5a8.json: SUCCESS in 9.01 seconds
3c9b0459.json: SUCCESS in 9.67 seconds
4258a5f9.json: SUCCESS in 7.54 seconds
42a50994.json: SUCCESS in 11.35 seconds
4347f46a.json: SUCCESS in 11.12 seconds
44f52bb0.json: SUCCESS in 7.51 seconds
46f33fce.json: SUCCESS in 16.56 seconds
4c4377d9.json: SUCCESS in 13.26 seconds
50cb2852.json: SUCCESS in 9.65 seconds
5582e5ca.json: SUCCESS in 7.79 seconds
5614dbcf.json: SUCCESS in 14.21 seconds
56ff96f3.json: SUCCESS in 9.32 seconds
5bd6f4ac.json: SUCCESS in 10.57 seconds
6150a2bd.json: SUCCESS in 9.85 seconds
62c24649.json: SUCCESS in 8.85 seconds
662c240a.json: SUCCESS in 9.70 seconds
67a3c6ac.json: SUCCESS in 12.53 seconds
67e8384a.json: SUCCESS in 8.92 seconds
68b16354.json: SUCCESS in 12.95 seconds
6d0aefbc.json: SUCCESS in 8.06 seconds
6f8cd79b.json: SUCCESS in 7.32 seconds
6fa7a44f.json: SUCCESS in 8.03 seconds
7468f01a.json: SUCCESS in 8.08 seconds
74dd1130.json: SUCCESS in 9.31 seconds
7b7f7511.json: SUCCESS in 8.41 seconds
8be77c9e.json: SUCCESS in 8.65 seconds
9172f3a0.json: SUCCESS in 8.04 seconds
9dfd6313.json: SUCCESS in 8.32 seconds
9ecd008a.json: SUCCESS in 24.14 seconds
a416b8f3.json: SUCCESS in 8.18 seconds
a699fb00.json: SUCCESS in 7.73 seconds
a740d043.json: SUCCESS in 20.27 seconds
a79310a0.json: SUCCESS in 7.40 seconds
ac0a08a4.json: SUCCESS in 8.05 seconds
aedd82e4.json: SUCCESS in 11.65 seconds
b1948b0a.json: SUCCESS in 8.76 seconds
b27ca6d3.json: SUCCESS in 11.68 seconds
b91ae062.json: SUCCESS in 7.99 seconds
bb43febb.json: SUCCESS in 8.50 seconds
be94b721.json: SUCCESS in 8.54 seconds
c1d99e64.json: SUCCESS in 27.96 seconds
c59eb873.json: SUCCESS in 22.75 seconds
c8f0f002.json: SUCCESS in 9.26 seconds
c909285e.json: SUCCESS in 19.77 seconds
c9e6f938.json: SUCCESS in 8.25 seconds
ce22a75a.json: SUCCESS in 8.50 seconds
d10ecb37.json: SUCCESS in 9.20 seconds
d511f180.json: SUCCESS in 8.96 seconds
dc1df850.json: SUCCESS in 24.41 seconds
ed36ccf7.json: SUCCESS in 10.30 seconds
f25fbde4.json: SUCCESS in 13.20 seconds
f25ffba3.json: SUCCESS in 10.23 seconds

Total verification time: 705.68 seconds