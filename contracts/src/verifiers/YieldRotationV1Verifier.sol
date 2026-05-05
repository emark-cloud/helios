// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract YieldRotationV1Verifier {
    // Scalar field size
    uint256 constant r =
        21_888_242_871_839_275_222_246_405_745_257_275_088_548_364_400_416_034_343_698_204_186_575_808_495_617;
    // Base field size
    uint256 constant q =
        21_888_242_871_839_275_222_246_405_745_257_275_088_696_311_157_297_823_662_689_037_894_645_226_208_583;

    // Verification Key data
    uint256 constant alphax =
        20_491_192_805_390_485_299_153_009_773_594_534_940_189_261_866_228_447_918_068_658_471_970_481_763_042;
    uint256 constant alphay =
        9_383_485_363_053_290_200_918_347_156_157_836_566_562_967_994_039_712_273_449_902_621_266_178_545_958;
    uint256 constant betax1 =
        4_252_822_878_758_300_859_123_897_981_450_591_353_533_073_413_197_771_768_651_442_665_752_259_397_132;
    uint256 constant betax2 =
        6_375_614_351_688_725_206_403_948_262_868_962_793_625_744_043_794_305_715_222_011_528_459_656_738_731;
    uint256 constant betay1 =
        21_847_035_105_528_745_403_288_232_691_147_584_728_191_162_732_299_865_338_377_159_692_350_059_136_679;
    uint256 constant betay2 =
        10_505_242_626_370_262_277_552_901_082_094_356_697_409_835_680_220_590_971_873_171_140_371_331_206_856;
    uint256 constant gammax1 =
        11_559_732_032_986_387_107_991_004_021_392_285_783_925_812_861_821_192_530_917_403_151_452_391_805_634;
    uint256 constant gammax2 =
        10_857_046_999_023_057_135_944_570_762_232_829_481_370_756_359_578_518_086_990_519_993_285_655_852_781;
    uint256 constant gammay1 =
        4_082_367_875_863_433_681_332_203_403_145_435_568_316_851_327_593_401_208_105_741_076_214_120_093_531;
    uint256 constant gammay2 =
        8_495_653_923_123_431_417_604_973_247_489_272_438_418_190_587_263_600_148_770_280_649_306_958_101_930;
    uint256 constant deltax1 =
        20_154_855_193_427_993_894_033_483_318_962_935_161_844_935_911_207_507_851_884_425_334_301_607_077_629;
    uint256 constant deltax2 =
        10_510_082_636_627_534_995_471_616_907_681_376_923_012_582_924_767_291_693_229_984_751_041_953_232_681;
    uint256 constant deltay1 =
        4_308_569_308_501_264_475_962_982_468_330_631_916_275_807_707_240_202_529_345_431_623_901_273_336_888;
    uint256 constant deltay2 =
        7_803_765_478_654_186_520_395_149_219_798_945_597_697_088_691_163_592_689_934_277_492_389_962_303_314;

    uint256 constant IC0x =
        21_152_039_512_914_452_690_853_869_996_443_862_302_826_618_096_055_573_569_177_747_646_114_243_165_514;
    uint256 constant IC0y =
        10_475_676_462_042_378_852_876_289_525_198_391_024_114_923_808_311_827_323_254_318_681_296_922_727_658;

    uint256 constant IC1x =
        18_677_398_824_990_031_091_268_371_220_523_180_363_191_891_632_876_752_059_158_865_180_929_868_279_952;
    uint256 constant IC1y =
        15_789_760_973_245_032_988_595_712_922_444_160_582_667_132_252_718_483_690_617_729_494_289_020_641_426;

    uint256 constant IC2x =
        9_513_953_457_653_580_921_589_081_667_736_098_508_878_346_544_861_888_327_115_897_922_323_018_461_217;
    uint256 constant IC2y =
        12_358_756_193_243_212_864_029_196_674_633_941_947_871_868_536_080_911_039_317_695_602_721_140_207_267;

    uint256 constant IC3x =
        21_289_540_406_232_270_299_973_740_026_623_005_220_576_116_381_410_119_597_318_257_688_270_126_353_622;
    uint256 constant IC3y =
        9_554_580_717_157_184_940_642_822_165_073_943_419_968_813_111_282_861_353_762_111_372_276_281_784_543;

    uint256 constant IC4x =
        7_064_146_677_496_166_584_731_450_692_989_100_127_113_498_418_895_751_117_277_873_207_952_129_500_101;
    uint256 constant IC4y =
        7_286_462_895_015_458_162_594_738_180_519_720_773_152_864_132_627_523_489_721_986_011_300_933_719_477;

    uint256 constant IC5x =
        5_235_905_707_510_277_578_645_074_421_475_325_565_701_279_038_449_866_749_641_334_917_791_443_402_840;
    uint256 constant IC5y =
        8_149_811_951_745_409_515_006_502_332_589_112_703_647_490_488_656_658_224_755_779_879_620_509_552_774;

    uint256 constant IC6x =
        9_592_268_454_486_445_775_082_206_504_164_446_774_956_941_245_220_811_742_567_393_552_669_726_020_969;
    uint256 constant IC6y =
        4_950_370_721_542_996_565_329_811_918_019_805_354_943_795_746_274_343_506_627_549_887_440_323_961_025;

    uint256 constant IC7x =
        13_236_313_963_185_344_821_671_303_840_375_510_076_729_669_065_305_679_857_318_187_584_023_531_646_959;
    uint256 constant IC7y =
        11_527_199_582_256_951_050_728_099_247_381_832_448_432_978_808_173_693_353_164_648_740_492_006_160_091;

    uint256 constant IC8x =
        9_749_022_414_059_486_411_550_196_467_861_139_635_559_917_586_329_767_207_668_372_529_078_808_361_225;
    uint256 constant IC8y =
        16_489_358_501_979_401_460_212_841_863_778_577_573_201_401_312_917_072_001_822_882_282_722_343_685_012;

    uint256 constant IC9x =
        18_054_039_142_645_208_745_623_818_444_557_349_367_053_472_464_819_324_174_095_357_076_721_828_432_063;
    uint256 constant IC9y =
        20_470_186_301_491_983_957_413_854_357_609_706_948_002_003_082_329_289_331_643_142_630_644_466_805_322;

    uint256 constant IC10x =
        21_453_866_492_941_850_213_038_600_614_613_476_712_737_991_374_775_605_646_360_586_960_520_292_262_840;
    uint256 constant IC10y =
        16_160_846_262_916_142_544_774_541_155_718_870_824_500_176_068_821_767_769_882_269_790_005_247_150_755;

    uint256 constant IC11x =
        11_061_045_829_492_442_470_540_311_826_964_439_949_116_741_428_373_817_235_266_357_120_844_682_574_065;
    uint256 constant IC11y =
        4_623_176_367_493_843_803_792_635_078_271_060_605_738_645_527_590_000_993_468_248_284_560_001_432_215;

    uint256 constant IC12x =
        1_400_702_559_786_599_738_157_330_970_929_797_451_032_138_766_159_497_130_135_548_336_667_365_437_772;
    uint256 constant IC12y =
        1_951_893_523_290_318_264_200_178_502_925_185_406_983_565_476_370_516_722_037_904_093_578_547_464_724;

    uint256 constant IC13x =
        13_488_552_526_079_159_827_789_886_777_069_915_386_006_201_557_062_518_028_817_055_397_995_684_652_992;
    uint256 constant IC13y =
        1_919_083_908_817_714_973_448_853_046_122_459_831_967_550_626_518_184_587_907_150_763_545_549_717_509;

    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[13] calldata _pubSignals
    ) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x

                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))

                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))

                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))

                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))

                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))

                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))

                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))

                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))

                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))

                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))

                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))

                g1_mulAccC(_pVk, IC12x, IC12y, calldataload(add(pubSignals, 352)))

                g1_mulAccC(_pVk, IC13x, IC13y, calldataload(add(pubSignals, 384)))

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))

                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)

                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F

            checkField(calldataload(add(_pubSignals, 0)))

            checkField(calldataload(add(_pubSignals, 32)))

            checkField(calldataload(add(_pubSignals, 64)))

            checkField(calldataload(add(_pubSignals, 96)))

            checkField(calldataload(add(_pubSignals, 128)))

            checkField(calldataload(add(_pubSignals, 160)))

            checkField(calldataload(add(_pubSignals, 192)))

            checkField(calldataload(add(_pubSignals, 224)))

            checkField(calldataload(add(_pubSignals, 256)))

            checkField(calldataload(add(_pubSignals, 288)))

            checkField(calldataload(add(_pubSignals, 320)))

            checkField(calldataload(add(_pubSignals, 352)))

            checkField(calldataload(add(_pubSignals, 384)))

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
            return(0, 0x20)
        }
    }
}
