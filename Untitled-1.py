def clacultae_strage(filesize):
    block_size = 4096
    full_blocks = filesize // block_size
    partial_block_remainder = filesize % block_size
    if partial_block_remainder > 0 :
        return ((partial_block_remainder * block_size) + block_size)
    else: 
        return (full_blocks * block_size)

print (clacultae_strage(1))
print (clacultae_strage(4096))
print (clacultae_strage(4097))
print (clacultae_strage(6000))
