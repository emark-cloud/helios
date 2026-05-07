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

contract MomentumV1Verifier {
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
        10_669_064_067_792_575_716_453_111_127_314_286_263_573_257_656_097_386_097_823_042_528_664_567_305_011;
    uint256 constant deltax2 =
        10_576_623_762_970_816_479_648_336_584_497_484_540_955_463_762_228_220_865_540_550_768_058_561_880_872;
    uint256 constant deltay1 =
        5_000_033_226_576_482_840_588_348_599_410_073_375_148_471_115_734_981_623_537_917_027_626_943_079_826;
    uint256 constant deltay2 =
        1_311_583_869_905_108_103_057_474_492_758_024_727_647_264_569_809_497_786_593_753_560_599_648_499_035;

    uint256 constant IC0x =
        15_807_001_356_503_561_181_287_730_165_202_859_646_506_856_739_146_368_189_912_559_749_638_802_321_173;
    uint256 constant IC0y =
        18_405_415_979_893_621_022_830_126_501_694_139_403_477_993_909_289_517_041_092_152_262_158_742_302_675;

    uint256 constant IC1x =
        17_106_644_562_938_389_731_860_673_231_631_748_884_236_516_773_064_910_494_058_590_544_237_763_497_469;
    uint256 constant IC1y =
        4_190_207_133_530_783_362_216_101_566_652_624_472_042_795_941_084_481_968_525_197_185_585_436_859_068;

    uint256 constant IC2x =
        19_058_690_042_403_383_831_557_064_262_174_789_006_300_347_434_372_983_392_551_203_814_466_053_005_412;
    uint256 constant IC2y =
        11_776_491_926_757_923_233_403_611_682_867_548_156_733_146_294_918_626_002_915_503_828_712_157_900_103;

    uint256 constant IC3x =
        6_399_930_214_990_911_465_440_107_630_700_555_568_845_514_791_893_180_462_952_086_383_706_278_243_307;
    uint256 constant IC3y =
        8_921_229_541_758_617_595_118_155_371_881_236_157_467_759_186_931_556_492_771_859_547_667_921_093_321;

    uint256 constant IC4x =
        11_401_492_504_509_516_461_310_000_928_638_450_637_663_841_646_143_835_358_086_586_614_034_495_719_589;
    uint256 constant IC4y =
        4_435_353_960_565_856_211_208_033_890_049_065_319_665_522_961_382_904_637_396_248_965_028_312_240_689;

    uint256 constant IC5x =
        10_443_955_067_411_296_571_634_312_013_127_628_627_877_993_293_964_668_230_910_964_066_918_659_113_512;
    uint256 constant IC5y =
        1_280_005_112_585_854_493_074_012_749_901_834_809_271_623_428_788_572_412_574_815_156_407_177_647_619;

    uint256 constant IC6x =
        19_077_995_519_831_576_674_737_240_782_368_924_413_444_455_081_372_026_914_277_693_187_359_683_387_481;
    uint256 constant IC6y =
        7_302_139_663_245_491_536_172_638_795_126_944_308_922_617_801_173_185_678_164_690_021_710_042_694_129;

    uint256 constant IC7x =
        13_970_446_770_863_743_471_467_473_846_362_550_956_876_167_288_404_813_454_813_512_328_064_208_593_632;
    uint256 constant IC7y =
        16_978_627_269_101_720_397_612_980_971_757_072_510_890_460_855_327_290_875_851_510_690_176_667_467_882;

    uint256 constant IC8x =
        7_769_523_925_315_458_315_995_046_058_704_856_509_115_627_568_594_489_726_686_018_426_873_315_855_339;
    uint256 constant IC8y =
        20_397_145_323_496_746_344_599_316_709_754_618_594_618_342_477_795_610_331_593_202_117_779_737_714_344;

    uint256 constant IC9x =
        9_999_187_065_200_310_069_822_430_384_991_201_138_793_487_568_040_344_799_113_591_327_626_909_244_722;
    uint256 constant IC9y =
        4_412_909_956_150_570_642_657_756_908_367_668_013_600_920_464_215_006_052_110_024_931_974_164_034_881;

    uint256 constant IC10x =
        18_320_453_661_639_718_345_598_086_782_344_618_861_062_862_666_236_727_490_550_677_818_546_269_777_198;
    uint256 constant IC10y =
        8_898_177_149_029_538_371_212_631_430_575_455_278_750_287_029_702_609_429_008_248_550_617_776_554_160;

    uint256 constant IC11x =
        5_455_395_970_269_041_577_642_211_096_298_143_987_727_635_156_672_315_681_028_177_072_932_758_358_141;
    uint256 constant IC11y =
        530_520_261_156_617_053_549_613_591_048_668_790_670_967_951_141_170_879_863_134_339_884_406_300_726;

    uint256 constant IC12x =
        20_103_002_204_066_942_122_460_268_672_417_255_933_279_463_927_264_834_229_310_284_632_045_279_812_396;
    uint256 constant IC12y =
        8_781_983_890_902_626_020_734_411_468_354_585_607_549_495_242_561_130_746_393_632_991_921_334_371_987;

    uint256 constant IC13x =
        14_999_936_688_851_784_742_520_785_101_690_650_016_970_416_277_007_564_948_097_542_644_079_782_798_009;
    uint256 constant IC13y =
        5_074_349_102_199_872_137_179_683_791_343_064_637_654_889_944_840_852_651_747_310_650_476_646_259_022;

    uint256 constant IC14x =
        9_597_314_995_825_122_609_208_227_124_293_153_528_423_955_801_907_656_227_083_131_551_516_896_316_505;
    uint256 constant IC14y =
        4_529_680_098_480_039_380_697_910_331_116_823_102_166_361_764_460_397_177_164_827_105_630_170_396_799;

    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[14] calldata _pubSignals
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

                g1_mulAccC(_pVk, IC14x, IC14y, calldataload(add(pubSignals, 416)))

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

            checkField(calldataload(add(_pubSignals, 416)))

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
            return(0, 0x20)
        }
    }
}
