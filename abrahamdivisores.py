def sum_divisords(n):
    sum=0
    i=1
    while i < n:
        modulo = n % i
        if modulo==0: sum= sum +i
        i+=1
    return sum
print(sum_divisords(0))
print(sum_divisords(3))
print(sum_divisords(36))
print(sum_divisords(102))


